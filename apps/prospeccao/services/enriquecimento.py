"""Enriquecimento de dados de empresas (CNPJ via BrasilAPI e helpers).

Todas as funções degradam com elegância: NUNCA levantam exceção para o
chamador — em erro retornam ``None`` ou valores vazios e registram no log.

Helpers expostos:
- :func:`extrair_cnpj_do_texto` — acha um CNPJ válido no HTML.
- :func:`consultar_cnpj` — consulta a BrasilAPI (data de fundação e sócios).
- :func:`tempo_de_mercado` — transforma uma data de fundação em "X anos".
- :func:`escolher_responsavel` — escolhe o sócio/responsável mais provável.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import requests

logger = logging.getLogger("modulos.prospeccao.enriquecimento")

_URL_BRASILAPI_CNPJ = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
_TIMEOUT_PADRAO = 10

# CNPJ com ou sem máscara: 00.000.000/0000-00 ou 00000000000000.
_RE_CNPJ = re.compile(r"\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b")

# Qualificações de sócio que indicam responsabilidade/comando (prioridade alta).
_CARGOS_PRIORITARIOS = (
    "administrador",
    "presidente",
    "diretor",
    "titular",
    "empresário",
    "sócio-administrador",
)


def _digitos(texto: str) -> str:
    """Mantém apenas dígitos de ``texto``."""
    return re.sub(r"\D", "", texto or "")


def _cnpj_valido(cnpj: str) -> bool:
    """Valida os dígitos verificadores do CNPJ (evita falsos positivos)."""
    c = _digitos(cnpj)
    if len(c) != 14 or len(set(c)) == 1:
        return False

    def _dv(base: str, pesos: list[int]) -> str:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    dv1 = _dv(c[:12], pesos1)
    dv2 = _dv(c[:12] + dv1, pesos2)
    return c[12] == dv1 and c[13] == dv2


def extrair_cnpj_do_texto(html: str) -> str | None:
    """Procura no HTML o primeiro CNPJ VÁLIDO e devolve só os 14 dígitos.

    Returns:
        String com 14 dígitos, ou ``None`` se nenhum CNPJ válido for achado.
    """
    if not html:
        return None
    try:
        for bruto in _RE_CNPJ.findall(html):
            digitos = _digitos(bruto)
            if len(digitos) == 14 and _cnpj_valido(digitos):
                return digitos
    except Exception:  # noqa: BLE001 - degrada em silêncio
        logger.warning("Falha ao extrair CNPJ do texto.", exc_info=False)
    return None


def _parse_data(valor: str | None) -> date | None:
    """Converte 'YYYY-MM-DD' (BrasilAPI) em ``date``; None se inválido."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def consultar_cnpj(cnpj: str, timeout: float = _TIMEOUT_PADRAO) -> dict:
    """Consulta a BrasilAPI para um CNPJ e normaliza o retorno.

    Returns:
        dict SEMPRE presente (degrada para vazios em erro) com as chaves:
            ``cnpj`` (str, 14 dígitos), ``razao_social`` (str),
            ``nome_fantasia`` (str), ``data_fundacao`` (date | None),
            ``socios`` (list[dict] com ``nome`` e ``cargo``).
    """
    vazio = {
        "cnpj": _digitos(cnpj),
        "razao_social": "",
        "nome_fantasia": "",
        "data_fundacao": None,
        "socios": [],
    }
    digitos = _digitos(cnpj)
    if len(digitos) != 14:
        logger.info("consultar_cnpj: CNPJ com tamanho inválido; ignorando.")
        return vazio

    url = _URL_BRASILAPI_CNPJ.format(cnpj=digitos)
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "modulosBot/1.0"},
        )
    except requests.RequestException as exc:
        logger.warning("consultar_cnpj: falha de rede (%s).", type(exc).__name__)
        return vazio

    if not resp.ok:
        logger.info("consultar_cnpj: BrasilAPI HTTP %s para o CNPJ informado.", resp.status_code)
        return vazio

    try:
        dados = resp.json() or {}
    except ValueError:
        logger.warning("consultar_cnpj: resposta não-JSON da BrasilAPI.")
        return vazio

    socios: list[dict] = []
    for socio in dados.get("qsa") or []:
        nome = (socio.get("nome_socio") or socio.get("nome") or "").strip()
        cargo = (socio.get("qualificacao_socio") or "").strip()
        if nome:
            socios.append({"nome": nome, "cargo": cargo})

    return {
        "cnpj": digitos,
        "razao_social": (dados.get("razao_social") or "").strip(),
        "nome_fantasia": (dados.get("nome_fantasia") or "").strip(),
        "data_fundacao": _parse_data(dados.get("data_inicio_atividade")),
        "socios": socios,
    }


def tempo_de_mercado(data_fundacao: date | None) -> str:
    """Transforma uma data de fundação em texto tipo "12 anos".

    Returns:
        "" se ``data_fundacao`` for inválida/futura; "menos de 1 ano",
        "1 ano" ou "N anos" caso contrário.
    """
    if not data_fundacao:
        return ""
    hoje = date.today()
    if data_fundacao > hoje:
        return ""
    anos = hoje.year - data_fundacao.year
    # Ajusta se ainda não fez aniversário neste ano.
    if (hoje.month, hoje.day) < (data_fundacao.month, data_fundacao.day):
        anos -= 1
    if anos <= 0:
        return "menos de 1 ano"
    if anos == 1:
        return "1 ano"
    return f"{anos} anos"


def escolher_responsavel(socios: list[dict] | None) -> str:
    """Escolhe o nome do responsável mais provável entre os sócios.

    Prioriza cargos de comando (administrador, presidente, diretor...). Sem
    correspondência, retorna o primeiro sócio. Vazio se não houver sócios.
    """
    if not socios:
        return ""
    for socio in socios:
        cargo = (socio.get("cargo") or "").lower()
        if any(chave in cargo for chave in _CARGOS_PRIORITARIOS):
            return socio.get("nome", "").strip()
    return (socios[0].get("nome") or "").strip()

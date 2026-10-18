"""Motor de análise (IA de regras) dos perfis da Google Places API (New).

Mede, para cada lugar retornado pela API, os critérios do módulo:

- ``rating`` abaixo do limite (padrão 4.0) ............... "Nota baixa";
- ``websiteUri`` ausente (null) .......................... "Sem site";
- ``userRatingCount`` abaixo do limite (padrão 5) ........ "Poucas avaliações";
- ``regularOpeningHours`` ausente ou mal preenchido ...... "Sem horário" / "Horário incompleto";
- ``businessStatus == CLOSED_PERMANENTLY`` ............... "Fechada permanentemente";
- ``photos`` ausentes ou em número muito baixo (padrão 3) "Poucas fotos";
- perfil sem atualização há mais de N meses (padrão 6) .. "Perfil desatualizado".

A Places API não informa a data da última edição do perfil. Como aproximação,
usa-se a data da avaliação mais recente (``reviews[].publishTime`` — a API
devolve até 5 avaliações). Sem avaliações datadas, não há atividade detectável
e o perfil é considerado desatualizado. A API também devolve no máximo 10
fotos por lugar, por isso o limite de fotos deve ficar entre 1 e 10.

Funções puras (sem banco e sem rede), reutilizadas pela busca, pela
reanálise de uma empresa e pelo recálculo das métricas:

- :func:`extrair_sinais` — converte o ``place`` cru da API em sinais simples;
- :func:`avaliar` — aplica os limites, gera alertas, score, prioridade e o
  diagnóstico em texto (com sugestões de abordagem).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.prospeccao.analise_places")

# Valores de ``businessStatus`` da Places API (New).
STATUS_OPERACIONAL = "OPERATIONAL"
STATUS_FECHADA_TEMPORARIAMENTE = "CLOSED_TEMPORARILY"
STATUS_FECHADA_PERMANENTEMENTE = "CLOSED_PERMANENTLY"

# Situação do horário de funcionamento (``regularOpeningHours``).
HORARIO_OK = "ok"
HORARIO_AUSENTE = "ausente"
HORARIO_INCOMPLETO = "incompleto"

# Menos dias com horário definido que isto = horário "mal preenchido".
DIAS_MINIMOS_HORARIO = 3

# Conversão de meses em dias para o critério de desatualização.
DIAS_POR_MES = 30.44

# Limites padrão (editáveis no Painel do módulo).
LIMIAR_NOTA_PADRAO = 4.0
LIMIAR_AVALIACOES_PADRAO = 5
LIMIAR_FOTOS_PADRAO = 3
LIMIAR_MESES_PADRAO = 6

# Pesos de cada alerta no score do perfil (0..100). "Fechada" zera o score.
PESOS: dict[str, int] = {
    "sem_site": 30,
    "nota_baixa": 15,
    "poucas_avaliacoes": 15,
    "sem_horario": 12,
    "horario_incompleto": 8,
    "poucas_fotos": 10,
    "perfil_desatualizado": 15,
}

# Sugestão de abordagem associada a cada alerta (chaves em textos.py).
_SUGESTOES: dict[str, str] = {
    "sem_site": "prospeccao.diagnostico.sug_sem_site",
    "nota_baixa": "prospeccao.diagnostico.sug_nota",
    "poucas_avaliacoes": "prospeccao.diagnostico.sug_avaliacoes",
    "sem_horario": "prospeccao.diagnostico.sug_horario",
    "horario_incompleto": "prospeccao.diagnostico.sug_horario",
    "poucas_fotos": "prospeccao.diagnostico.sug_fotos",
    "perfil_desatualizado": "prospeccao.diagnostico.sug_atualizacao",
}

PRIORIDADE_ALTA = "alta"
PRIORIDADE_MEDIA = "media"
PRIORIDADE_BAIXA = "baixa"
PRIORIDADE_DESCARTAR = "descartar"


@dataclass(frozen=True)
class Limiares:
    """Limites usados na classificação dos perfis."""

    nota: float = LIMIAR_NOTA_PADRAO
    avaliacoes: int = LIMIAR_AVALIACOES_PADRAO
    fotos: int = LIMIAR_FOTOS_PADRAO
    meses: int = LIMIAR_MESES_PADRAO

    @classmethod
    def de_config(cls, config: Any) -> "Limiares":
        """Monta os limites a partir de ``ConfiguracaoProspeccao`` (tolerante)."""
        if config is None:
            return cls()
        try:
            return cls(
                nota=float(getattr(config, "limiar_nota", LIMIAR_NOTA_PADRAO)),
                avaliacoes=int(getattr(config, "limiar_avaliacoes", LIMIAR_AVALIACOES_PADRAO)),
                fotos=int(getattr(config, "limiar_fotos", LIMIAR_FOTOS_PADRAO)),
                meses=int(getattr(config, "limiar_meses", LIMIAR_MESES_PADRAO)),
            )
        except (TypeError, ValueError):
            logger.warning("Limiares inválidos na configuração; usando os padrões.")
            return cls()


def dias_por_meses(meses: Any) -> int:
    """Converte meses em dias (mínimo 1)."""
    try:
        return max(1, round(float(meses) * DIAS_POR_MES))
    except (TypeError, ValueError):
        return round(LIMIAR_MESES_PADRAO * DIAS_POR_MES)


# ---------------------------------------------------------------------------
# Extração dos sinais
# ---------------------------------------------------------------------------
def _float(valor: Any) -> float | None:
    try:
        return float(valor) if valor is not None and valor != "" else None
    except (TypeError, ValueError):
        return None


def _int(valor: Any) -> int | None:
    try:
        return int(valor) if valor is not None and valor != "" else None
    except (TypeError, ValueError):
        return None


def _minutos(ponto: dict) -> int:
    """Minutos desde 00:00 de um ponto ``{day, hour, minute}`` (ausente = 0)."""
    return (_int(ponto.get("hour")) or 0) * 60 + (_int(ponto.get("minute")) or 0)


def _eh_24_horas(periodo: dict) -> bool:
    """Período único que abre domingo 00:00 e não fecha = aberto 24h/7 dias."""
    abre = periodo.get("open")
    return (
        isinstance(abre, dict)
        and not periodo.get("close")
        and (_int(abre.get("day")) or 0) == 0
        and _minutos(abre) == 0
    )


def avaliar_horario(horario: Any) -> tuple[str, list[str]]:
    """Classifica ``regularOpeningHours`` em ok / ausente / incompleto.

    Retorna ``(situacao, descricoes_da_semana)``. "Incompleto" (mal preenchido)
    quando: não há períodos; algum período não tem abertura ou fechamento (fora
    o caso 24h); abertura e fechamento coincidem; as descrições da semana não
    cobrem os 7 dias; ou menos de ``DIAS_MINIMOS_HORARIO`` dias têm horário.
    """
    if not isinstance(horario, dict) or not horario:
        return HORARIO_AUSENTE, []

    semana = [
        str(d).strip() for d in (horario.get("weekdayDescriptions") or []) if str(d).strip()
    ]
    periodos = horario.get("periods")
    if not isinstance(periodos, list):
        periodos = []

    if not periodos and not semana:
        return HORARIO_AUSENTE, semana
    if not periodos:
        return HORARIO_INCOMPLETO, semana
    if len(periodos) == 1 and isinstance(periodos[0], dict) and _eh_24_horas(periodos[0]):
        return HORARIO_OK, semana

    dias: set[int] = set()
    for periodo in periodos:
        if not isinstance(periodo, dict):
            return HORARIO_INCOMPLETO, semana
        abre, fecha = periodo.get("open"), periodo.get("close")
        if not isinstance(abre, dict) or not isinstance(fecha, dict):
            return HORARIO_INCOMPLETO, semana
        mesmo_dia = (_int(abre.get("day")) or 0) == (_int(fecha.get("day")) or 0)
        if mesmo_dia and _minutos(abre) == _minutos(fecha):
            return HORARIO_INCOMPLETO, semana
        dias.add(_int(abre.get("day")) or 0)

    if semana and len(semana) != 7:
        return HORARIO_INCOMPLETO, semana
    if len(dias) < DIAS_MINIMOS_HORARIO:
        return HORARIO_INCOMPLETO, semana
    return HORARIO_OK, semana


def ultima_atividade(avaliacoes: Any) -> date | None:
    """Data da avaliação mais recente (``reviews[].publishTime``) ou ``None``."""
    mais_recente: date | None = None
    for avaliacao in avaliacoes if isinstance(avaliacoes, list) else []:
        if not isinstance(avaliacao, dict):
            continue
        bruto = str(avaliacao.get("publishTime") or "")[:10]
        try:
            data = date.fromisoformat(bruto)
        except ValueError:
            continue
        if mais_recente is None or data > mais_recente:
            mais_recente = data
    return mais_recente


def extrair_sinais(place: Any) -> dict[str, Any]:
    """Extrai os sinais analisados de um ``place`` cru da Places API (New)."""
    place = place if isinstance(place, dict) else {}
    fotos = place.get("photos")
    situacao, semana = avaliar_horario(place.get("regularOpeningHours"))
    return {
        "nota": _float(place.get("rating")),
        "total_avaliacoes": _int(place.get("userRatingCount")) or 0,
        "total_fotos": len(fotos) if isinstance(fotos, list) else 0,
        "website": str(place.get("websiteUri") or "").strip(),
        "status_google": str(place.get("businessStatus") or "").strip().upper(),
        "situacao_horario": situacao,
        "horario_semana": semana[:7],
        "ultima_atividade": ultima_atividade(place.get("reviews")),
        "google_maps_url": str(place.get("googleMapsUri") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Avaliação (alertas, score, prioridade e diagnóstico)
# ---------------------------------------------------------------------------
def _numero_br(valor: float) -> str:
    """Formata ``4.0`` como ``"4,0"``."""
    return f"{float(valor):.1f}".replace(".", ",")


def _prioridade(score: int, fechada: bool) -> str:
    if fechada:
        return PRIORIDADE_DESCARTAR
    if score >= 60:
        return PRIORIDADE_ALTA
    if score >= 30:
        return PRIORIDADE_MEDIA
    return PRIORIDADE_BAIXA


def avaliar(
    sinais: dict[str, Any],
    limiares: Limiares | None = None,
    hoje: date | None = None,
) -> dict[str, Any]:
    """Aplica os limites aos ``sinais`` e devolve o resultado da análise.

    Retorna::

        {
            "alertas": ["nota_baixa", ...],    # slugs, na ordem de relevância
            "descricoes": ["nota 3,6 ...", ...],
            "score": 0..100,                    # quanto maior, mais oportunidade
            "prioridade": "alta"|"media"|"baixa"|"descartar",
            "fechada": bool,
            "diagnostico": "texto em PT-BR",
        }
    """
    limiares = limiares or Limiares()
    hoje = hoje or date.today()
    alertas: list[str] = []
    descricoes: list[str] = []

    def alerta(slug: str, descricao: str) -> None:
        alertas.append(slug)
        descricoes.append(descricao)

    fechada = (sinais.get("status_google") or "") == STATUS_FECHADA_PERMANENTEMENTE

    if not (sinais.get("website") or "").strip():
        alerta("sem_site", texto("prospeccao.diagnostico.sem_site"))

    nota = _float(sinais.get("nota"))
    if nota is not None and nota < limiares.nota:
        alerta(
            "nota_baixa",
            texto(
                "prospeccao.diagnostico.nota_baixa",
                nota=_numero_br(nota),
                limite=_numero_br(limiares.nota),
            ),
        )

    total = _int(sinais.get("total_avaliacoes"))
    if total is not None and total < limiares.avaliacoes:
        alerta(
            "poucas_avaliacoes",
            texto("prospeccao.diagnostico.sem_avaliacoes")
            if total == 0
            else texto(
                "prospeccao.diagnostico.poucas_avaliacoes",
                quantidade=total,
                limite=limiares.avaliacoes,
            ),
        )

    situacao = sinais.get("situacao_horario") or ""
    if situacao == HORARIO_AUSENTE:
        alerta("sem_horario", texto("prospeccao.diagnostico.sem_horario"))
    elif situacao == HORARIO_INCOMPLETO:
        alerta("horario_incompleto", texto("prospeccao.diagnostico.horario_incompleto"))

    fotos = _int(sinais.get("total_fotos"))
    if fotos is not None and fotos < limiares.fotos:
        alerta(
            "poucas_fotos",
            texto("prospeccao.diagnostico.sem_fotos")
            if fotos == 0
            else texto(
                "prospeccao.diagnostico.poucas_fotos", quantidade=fotos, limite=limiares.fotos
            ),
        )

    atividade = sinais.get("ultima_atividade")
    if isinstance(atividade, str):
        try:
            atividade = date.fromisoformat(atividade[:10])
        except ValueError:
            atividade = None
    if not isinstance(atividade, date):
        alerta("perfil_desatualizado", texto("prospeccao.diagnostico.sem_atividade"))
    else:
        dias = (hoje - atividade).days
        if dias > dias_por_meses(limiares.meses):
            alerta(
                "perfil_desatualizado",
                texto(
                    "prospeccao.diagnostico.desatualizado",
                    meses=max(1, round(dias / DIAS_POR_MES)),
                    limite=limiares.meses,
                ),
            )

    score = 0 if fechada else min(100, sum(PESOS.get(slug, 0) for slug in alertas))
    prioridade = _prioridade(score, fechada)
    return {
        "alertas": alertas,
        "descricoes": descricoes,
        "score": score,
        "prioridade": prioridade,
        "fechada": fechada,
        "diagnostico": montar_diagnostico(alertas, descricoes, score, prioridade, fechada),
    }


def montar_diagnostico(
    alertas: list[str],
    descricoes: list[str],
    score: int,
    prioridade: str,
    fechada: bool,
) -> str:
    """Texto do diagnóstico do motor de regras (PT-BR, centralizado em textos.py)."""
    partes: list[str] = []
    if fechada:
        partes.append(texto("prospeccao.diagnostico.fechada"))
    if descricoes:
        partes.append(texto("prospeccao.diagnostico.cabecalho", itens="; ".join(descricoes)))
    else:
        partes.append(texto("prospeccao.diagnostico.sem_alertas"))
    partes.append(
        texto(
            "prospeccao.diagnostico.prioridade",
            prioridade=texto(f"prospeccao.diagnostico.prioridade_{prioridade}"),
            score=score,
        )
    )
    if not fechada:
        sugestoes: list[str] = []
        for slug in alertas:
            chave = _SUGESTOES.get(slug)
            sugestao = texto(chave) if chave else ""
            if sugestao and sugestao not in sugestoes:
                sugestoes.append(sugestao)
        if sugestoes:
            partes.append(texto("prospeccao.diagnostico.sugestoes", itens="; ".join(sugestoes)))
    return " ".join(partes)

"""Orquestrador da análise de uma empresa (núcleo técnico do módulo).

:func:`analisar_empresa` encadeia todas as etapas — métricas da Google Places
API (New), download SEGURO do site (sempre via
``seguranca_rede.requisicao_segura``, nunca ``requests`` direto), análise de
HTML, PageSpeed, enriquecimento por CNPJ — aplica o motor de análise
(``analise_places``: nota, avaliações, site, horário, situação, fotos e
atualização do perfil), calcula as flags, o diagnóstico e o
``oportunidade_score`` e SALVA a empresa.

Também expõe:
- :func:`aplicar_sinais_places` — grava na empresa as métricas do Places;
- :func:`atualizar_dados_google` — Place Details + reanálise de uma empresa;
- :func:`recalcular_empresa` — recalcula diagnóstico/score sem rede;
- :func:`dados_para_ia` — dados estruturados enviados à IA generativa.

Características:
- Resiliente: cada etapa roda em ``try/except`` próprio; a falha de uma etapa
  não impede as demais nem o salvamento.
- Idempotente: reexecutar recomputa os mesmos campos a partir do estado atual.
- Seguro: segredos nunca vão para o log; todo fetch externo passa pelo fetcher
  anti-SSRF.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from . import credenciais, google_places, pagespeed
from .analise_places import (
    PESOS,
    STATUS_FECHADA_PERMANENTEMENTE,
    Limiares,
    avaliar,
)
from .analise_site import analisar_html
from .enriquecimento import (
    consultar_cnpj,
    escolher_responsavel,
    extrair_cnpj_do_texto,
    tempo_de_mercado,
)
from .seguranca_rede import ErroRequisicaoSegura, RespostaSegura, requisicao_segura

if TYPE_CHECKING:  # apenas para type hints; sem acoplamento em tempo de execução
    from apps.prospeccao.models import ConexaoGoogle, ConfiguracaoProspeccao, Empresa

logger = logging.getLogger("modulos.prospeccao.orquestrador")


def _txt(valor: object) -> str:
    """Normaliza um valor possivelmente ``None`` para texto sem espaços nas pontas."""
    return (valor or "").strip() if isinstance(valor, str) else ("" if valor is None else str(valor).strip())


def _dominio_simples(url: str) -> str:
    """Domínio a partir da URL (fallback quando não houve análise de HTML)."""
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def campos_places(dados: dict) -> dict:
    """Campos da ``Empresa`` com as métricas da Google Places API.

    ``dados`` é o retorno de ``google_places._normalizar`` (busca ou detalhes).
    Os valores do Google são a fonte da verdade: ausência vira ``None``/vazio.
    """
    return {
        "nota_google": dados.get("nota"),
        "total_avaliacoes": dados.get("total_avaliacoes"),
        "total_fotos": dados.get("total_fotos"),
        "status_google": _txt(dados.get("status_google"))[:30],
        "situacao_horario": _txt(dados.get("situacao_horario"))[:12],
        "horario_semana": [str(d)[:120] for d in (dados.get("horario_semana") or [])][:7],
        "ultima_atividade_perfil": dados.get("ultima_atividade"),
        "google_maps_url": _txt(dados.get("google_maps_url"))[:500],
        "analisado_places_em": timezone.now(),
    }


def aplicar_sinais_places(empresa: "Empresa", dados: dict) -> None:
    """Grava na instância da empresa as métricas da Google Places API."""
    for campo, valor in campos_places(dados).items():
        setattr(empresa, campo, valor)


def _completar_via_place_details(empresa: "Empresa", conexao: "ConexaoGoogle | None") -> None:
    """Busca as métricas do Places de empresas ainda não analisadas (best-effort).

    Resultados de busca já trazem todos os campos do Text Search; este passo só
    consulta o Place Details para empresas antigas/sem métricas do Google.
    """
    if not _txt(getattr(empresa, "place_id", "")) or empresa.analisado_places_em is not None:
        return
    chave = credenciais.chave_google(conexao)
    if not chave:
        return
    try:
        detalhe = google_places.detalhes(chave, empresa.place_id)
    except Exception:  # noqa: BLE001 - etapa opcional; não interrompe a análise
        logger.warning("Place Details falhou; seguindo sem completar dados.", exc_info=True)
        return
    if not detalhe:
        return
    if detalhe.get("website") and not _txt(empresa.website):
        empresa.website = detalhe["website"][:300]
    if detalhe.get("telefone") and not _txt(empresa.telefone):
        empresa.telefone = detalhe["telefone"][:50]
    aplicar_sinais_places(empresa, detalhe)


def _baixar_site(website: str) -> RespostaSegura | None:
    """Baixa o site pelo fetcher seguro. Retorna None em recusa/falha."""
    try:
        return requisicao_segura(website)
    except ErroRequisicaoSegura as exc:
        logger.warning("Fetch seguro recusou/falhou (%s): %s", website, exc)
    except Exception:  # noqa: BLE001 - qualquer imprevisto vira "sem site analisável"
        logger.warning("Erro inesperado ao baixar o site %s.", website, exc_info=True)
    return None


def _aplicar_analise(empresa: "Empresa", analise: dict) -> None:
    """Grava no ``empresa`` os campos derivados da análise de HTML."""
    empresa.site_desatualizado = bool(analise["site_desatualizado"])
    empresa.apenas_instagram = bool(analise["apenas_instagram"])
    empresa.score_seo = int(analise["score_seo"])

    # Contatos: só preenche lacunas (preserva dados já existentes / do Google).
    if not _txt(empresa.email) and analise["emails"]:
        empresa.email = sorted(analise["emails"])[0]
    if not _txt(empresa.instagram) and analise["instagram"]:
        empresa.instagram = analise["instagram"]
    if not _txt(empresa.whatsapp) and analise["whatsapp"]:
        empresa.whatsapp = analise["whatsapp"]
    if not _txt(empresa.dominio) and analise["dominio"]:
        empresa.dominio = analise["dominio"]

    # Hospedagem sem site: página no ar, porém "pobre" (sem título/H1/descrição)
    # e que não é apenas um redirecionamento para o Instagram/Linktree.
    conteudo_pobre = (
        not _txt(analise["titulo"])
        and not analise["tem_h1"]
        and not _txt(analise["meta_description"])
    )
    empresa.hospedagem_sem_site = bool(conteudo_pobre and not analise["apenas_instagram"])


def _defaults_sem_site(empresa: "Empresa", website: str) -> None:
    """Define flags quando não há site analisável."""
    empresa.site_desatualizado = False
    empresa.score_seo = None
    empresa.hospedagem_sem_site = False
    empresa.apenas_instagram = (not empresa.tem_site) and bool(_txt(empresa.instagram))
    if not _txt(empresa.dominio) and website:
        empresa.dominio = _dominio_simples(website)


def _enriquecer_por_cnpj(empresa: "Empresa", resposta: RespostaSegura) -> None:
    """Extrai CNPJ do HTML e enriquece fundação/tempo de mercado/responsável."""
    cnpj = extrair_cnpj_do_texto(resposta.html)
    if not cnpj:
        return
    dados = consultar_cnpj(cnpj)

    data_fundacao = dados.get("data_fundacao")
    if data_fundacao:
        empresa.data_fundacao = data_fundacao
        empresa.tempo_mercado_texto = tempo_de_mercado(data_fundacao)

    socios = dados.get("socios") or []
    nome_resp = escolher_responsavel(socios)
    if nome_resp and not _txt(empresa.responsavel):
        empresa.responsavel = nome_resp
        for socio in socios:
            if socio.get("nome") == nome_resp and socio.get("cargo"):
                if not _txt(empresa.cargo_responsavel):
                    empresa.cargo_responsavel = socio["cargo"]
                break


def _sinais_da_empresa(empresa: "Empresa") -> dict:
    """Sinais do motor de análise a partir dos campos já gravados na empresa."""
    return {
        "nota": empresa.nota_google,
        "total_avaliacoes": empresa.total_avaliacoes,
        "total_fotos": empresa.total_fotos,
        "website": empresa.website,
        "status_google": empresa.status_google,
        "situacao_horario": empresa.situacao_horario,
        "ultima_atividade": empresa.ultima_atividade_perfil,
    }


def avaliar_perfil_google(
    empresa: "Empresa", config: "ConfiguracaoProspeccao | None" = None
) -> dict | None:
    """Aplica o motor de análise às métricas do Google e grava o diagnóstico.

    Retorna o resultado de ``analise_places.avaliar`` ou ``None`` quando a
    empresa ainda não tem métricas da Google Places API.
    """
    if empresa.analisado_places_em is None:
        return None
    if config is None:
        from apps.prospeccao.models import ConfiguracaoProspeccao

        config = ConfiguracaoProspeccao.obter()
    resultado = avaliar(
        _sinais_da_empresa(empresa), Limiares.de_config(config), hoje=timezone.localdate()
    )
    empresa.diagnostico = resultado["diagnostico"]
    return resultado


def _pontos_google(resultado: dict | None) -> int:
    """Pontos do perfil no Google (sem repetir "sem site", já contado no site)."""
    if not resultado:
        return 0
    return sum(PESOS.get(slug, 0) for slug in resultado["alertas"] if slug != "sem_site")


def _calcular_oportunidade(empresa: "Empresa", resultado_google: dict | None = None) -> int:
    """Pontua a oportunidade (0..100): mais problemas -> maior a oportunidade.

    Combina os problemas do site com os alertas do perfil no Google. Empresas
    fechadas permanentemente não são oportunidade (score 0).
    """
    if empresa.status_google == STATUS_FECHADA_PERMANENTEMENTE:
        return 0
    score = _pontos_google(resultado_google)
    if not empresa.tem_site:
        score += 40  # ausência de site é o maior gancho comercial
    else:
        if empresa.site_desatualizado:
            score += 20
        if empresa.tem_ssl is False:
            score += 15
        if empresa.score_seo is not None and empresa.score_seo < 50:
            score += 15
        if empresa.score_performance is not None and empresa.score_performance < 50:
            score += 10
        if empresa.hospedagem_sem_site:
            score += 15
    if empresa.apenas_instagram:
        score += 20
    return max(0, min(100, score))


def analisar_empresa(empresa: "Empresa", conexao: "ConexaoGoogle | None" = None) -> "Empresa":
    """Analisa uma empresa de ponta a ponta e a salva.

    Args:
        empresa: instância de ``Empresa`` (persistida ou não) a analisar.
        conexao: ``ConexaoGoogle`` opcional, usada apenas para buscar no Place
            Details as métricas de empresas ainda não analisadas no Google
            (sem conexão, vale a chave do Painel do módulo).

    Returns:
        A mesma instância ``empresa``, já salva e com os campos preenchidos.
    """
    logger.info(
        "Iniciando análise: empresa pk=%s nome=%r",
        getattr(empresa, "pk", None),
        _txt(getattr(empresa, "nome", "")),
    )

    # Etapa 0 — completar website/telefone via Place Details (opcional).
    try:
        _completar_via_place_details(empresa, conexao)
    except Exception:  # noqa: BLE001 - blindagem extra por etapa
        logger.warning("Etapa Place Details lançou exceção inesperada.", exc_info=True)

    website = _txt(empresa.website)
    resposta: RespostaSegura | None = None

    # Etapa 1 — download seguro + análise de HTML.
    if website:
        resposta = _baixar_site(website)
        if resposta is not None:
            empresa.tem_site = True
            empresa.tem_ssl = resposta.tem_ssl
            try:
                analise = analisar_html(resposta.html, resposta.url_final)
                _aplicar_analise(empresa, analise)
                logger.debug("Análise de HTML aplicada para %s.", empresa.dominio)
            except Exception:  # noqa: BLE001 - análise falhou; mantém flags neutras
                logger.warning("Análise de HTML falhou; usando defaults.", exc_info=True)
                _defaults_sem_site(empresa, website)
        else:
            empresa.tem_site = False
            empresa.tem_ssl = None
            _defaults_sem_site(empresa, website)
    else:
        empresa.tem_site = False
        empresa.tem_ssl = None
        _defaults_sem_site(empresa, website)

    # Etapa 2 — PageSpeed (degrada para None sem chave/erro).
    empresa.score_performance = None
    if empresa.tem_site and website:
        alvo = resposta.url_final if resposta is not None else website
        chave_ps = getattr(settings, "GOOGLE_PAGESPEED_API_KEY", "")
        try:
            empresa.score_performance = pagespeed.pontuar(alvo, chave_ps)
        except Exception:  # noqa: BLE001 - pontuar já degrada; blindagem extra
            logger.warning("Etapa PageSpeed lançou exceção inesperada.", exc_info=True)

    # Etapa 3 — enriquecimento por CNPJ (a partir do HTML baixado).
    if resposta is not None:
        try:
            _enriquecer_por_cnpj(empresa, resposta)
        except Exception:  # noqa: BLE001 - enriquecimento é best-effort
            logger.warning("Etapa de enriquecimento (CNPJ) falhou.", exc_info=True)

    # Recalcula o texto de tempo de mercado se houver data e ele estiver vazio.
    if empresa.data_fundacao and not _txt(empresa.tempo_mercado_texto):
        empresa.tempo_mercado_texto = tempo_de_mercado(empresa.data_fundacao)

    # Etapa 4 — motor de análise do perfil no Google + pontuação de oportunidade.
    resultado_google = None
    try:
        resultado_google = avaliar_perfil_google(empresa)
    except Exception:  # noqa: BLE001 - o motor nunca deve impedir o salvamento
        logger.warning("Motor de análise do perfil no Google falhou.", exc_info=True)
    empresa.oportunidade_score = _calcular_oportunidade(empresa, resultado_google)
    _descartar_se_fechada(empresa)
    logger.info(
        "Análise concluída: empresa pk=%s tem_site=%s ssl=%s seo=%s perf=%s oportunidade=%s",
        getattr(empresa, "pk", None),
        empresa.tem_site,
        empresa.tem_ssl,
        empresa.score_seo,
        empresa.score_performance,
        empresa.oportunidade_score,
    )

    # Etapa 5 — persistência (falha de DB propaga: é erro real, não de etapa).
    try:
        empresa.save()
    except Exception:
        logger.exception("Falha ao salvar a empresa após a análise.")
        raise
    return empresa


def _descartar_se_fechada(empresa: "Empresa") -> None:
    """Leads novos de empresas fechadas permanentemente viram "descartada"."""
    from apps.prospeccao.models import Empresa as ModeloEmpresa

    if (
        empresa.status_google == STATUS_FECHADA_PERMANENTEMENTE
        and empresa.status_prospeccao == ModeloEmpresa.Status.NOVA
    ):
        empresa.status_prospeccao = ModeloEmpresa.Status.DESCARTADA


def atualizar_dados_google(
    empresa: "Empresa", conexao: "ConexaoGoogle | None" = None
) -> "Empresa":
    """Consulta o Place Details da empresa, grava as métricas e reanalisa tudo.

    Raises:
        google_places.ErroConfiguracao: sem chave, chave inválida ou erro da API.
        ValueError: a empresa não tem ``place_id``.
    """
    place_id = _txt(empresa.place_id)
    if not place_id:
        raise ValueError("Empresa sem place_id.")
    detalhe = google_places.detalhes(credenciais.chave_google(conexao), place_id)
    if detalhe:
        for campo, chave, limite in (
            ("endereco", "endereco", 255),
            ("telefone", "telefone", 50),
            ("categoria", "categoria", 150),
        ):
            if _txt(detalhe.get(chave)):
                setattr(empresa, campo, _txt(detalhe.get(chave))[:limite])
        # O website do perfil é a fonte da verdade do critério "websiteUri nulo".
        empresa.website = _txt(detalhe.get("website"))[:300]
        if detalhe.get("lat") is not None and detalhe.get("lng") is not None:
            empresa.latitude = detalhe["lat"]
            empresa.longitude = detalhe["lng"]
        aplicar_sinais_places(empresa, detalhe)
    return analisar_empresa(empresa, conexao)


def recalcular_empresa(
    empresa: "Empresa", config: "ConfiguracaoProspeccao | None" = None
) -> "Empresa":
    """Recalcula diagnóstico e score com os limites atuais (sem acessar a rede)."""
    resultado_google = avaliar_perfil_google(empresa, config)
    empresa.oportunidade_score = _calcular_oportunidade(empresa, resultado_google)
    _descartar_se_fechada(empresa)
    empresa.save(update_fields=["diagnostico", "oportunidade_score", "status_prospeccao", "atualizado_em"])
    return empresa


def dados_para_ia(empresa: "Empresa", config: "ConfiguracaoProspeccao | None" = None) -> dict:
    """Dados estruturados (sem segredos) enviados à IA generativa."""
    return {
        "nome": empresa.nome,
        "categoria": empresa.categoria,
        "endereco": empresa.endereco,
        "website": empresa.website or None,
        "perfil_google": {
            "nota": empresa.nota_google,
            "total_avaliacoes": empresa.total_avaliacoes,
            "total_fotos": empresa.total_fotos,
            "situacao": empresa.status_google or None,
            "horario": empresa.situacao_horario or None,
            "horario_semana": empresa.horario_semana or [],
            "ultima_avaliacao": empresa.ultima_atividade_perfil.isoformat()
            if empresa.ultima_atividade_perfil
            else None,
        },
        "site": {
            "tem_site": empresa.tem_site,
            "tem_ssl": empresa.tem_ssl,
            "score_seo": empresa.score_seo,
            "score_performance": empresa.score_performance,
            "site_desatualizado": empresa.site_desatualizado,
            "apenas_instagram": empresa.apenas_instagram,
        },
        "problemas_detectados": empresa.rotulos_problemas(config),
        "diagnostico_do_motor_de_regras": empresa.diagnostico or None,
        "score_de_oportunidade": empresa.oportunidade_score,
    }

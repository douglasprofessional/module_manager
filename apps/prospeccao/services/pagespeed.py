"""Pontuação de performance via Google PageSpeed Insights API.

Degrada com elegância: sem chave, sem URL válida ou em qualquer erro/tempo
esgotado, retorna ``None`` (nunca levanta para o chamador). A chave NUNCA é
registrada em log.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger("modulos.prospeccao.pagespeed")

_URL_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_TIMEOUT_PADRAO = 30


def pontuar(
    url: str,
    chave: str | None,
    estrategia: str = "mobile",
    timeout: float = _TIMEOUT_PADRAO,
) -> int | None:
    """Retorna a nota de performance (0..100) de ``url``, ou ``None``.

    Args:
        url: endereço do site a avaliar.
        chave: chave da PageSpeed Insights API (opcional; sem ela retorna None).
        estrategia: "mobile" (padrão) ou "desktop".
        timeout: timeout da chamada em segundos (a API pode ser lenta).

    Returns:
        Inteiro 0..100 com a nota de performance, ou ``None`` se indisponível.
    """
    url = (url or "").strip()
    chave = (chave or "").strip()
    if not url:
        logger.debug("PageSpeed: URL vazia; retornando None.")
        return None
    if not chave:
        logger.info("PageSpeed: sem chave de API; pulando (retorna None).")
        return None

    parametros = {
        "url": url,
        "key": chave,
        "category": "PERFORMANCE",
        "strategy": estrategia,
    }
    try:
        resp = requests.get(_URL_API, params=parametros, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("PageSpeed: falha de rede (%s); retornando None.", type(exc).__name__)
        return None

    if not resp.ok:
        # Não loga o corpo (a query, já enviada, contém a chave).
        logger.warning("PageSpeed: HTTP %s; retornando None.", resp.status_code)
        return None

    try:
        dados = resp.json() or {}
        bruto = dados["lighthouseResult"]["categories"]["performance"]["score"]
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("PageSpeed: resposta inesperada (%s); retornando None.", type(exc).__name__)
        return None

    if bruto is None:
        return None
    try:
        return max(0, min(100, round(float(bruto) * 100)))
    except (TypeError, ValueError):
        return None

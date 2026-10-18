"""Integração com a Google Places API (New) — Text Search + Place Details.

Usa a Places API (New) v1 via ``requests`` — sem SDK pesado. A chave de API
NUNCA é registrada em log; trafega apenas no cabeçalho ``X-Goog-Api-Key``.

Funções principais:
- :func:`buscar_empresas` — busca textual paginada (até 60 lugares, 3 páginas
  de 20) com ``locationBias`` circular quando a localização é encontrada.
- :func:`detalhes` — Place Details de um ``place_id`` (reanálise).
- :func:`testar_chave` — verificação rápida da chave (campo ``places.id``).

Ambas normalizam o retorno para um ``dict`` com chaves estáveis:
``place_id, nome, endereco, telefone, website, lat, lng, categoria`` e as
métricas analisadas pelo motor (``services.analise_places``): ``nota,
total_avaliacoes, total_fotos, status_google, situacao_horario,
horario_semana, ultima_atividade, google_maps_url``.

Campos pedidos (FieldMask) e o que medem:
``rating`` (nota), ``userRatingCount`` (nº de avaliações), ``websiteUri``
(site; ausente = null), ``regularOpeningHours`` (horário), ``businessStatus``
(ex.: CLOSED_PERMANENTLY), ``photos`` (até 10) e ``reviews`` (até 5, cuja
``publishTime`` mais recente aproxima a última atualização do perfil).
Observação de custo: ``reviews`` e ``regularOpeningHours`` pertencem às
faixas mais caras (Enterprise/Atmosphere) da Places API.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from apps.nucleo.textos import texto

from .analise_places import extrair_sinais

logger = logging.getLogger("modulos.prospeccao.google_places")

# Places API (New) v1.
_BASE = "https://places.googleapis.com/v1"
_URL_TEXT_SEARCH = f"{_BASE}/places:searchText"

# Campos pedidos à API. No Text Search o FieldMask exige o prefixo "places.".
_CAMPOS = (
    "id",
    "displayName",
    "formattedAddress",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "websiteUri",
    "location",
    "primaryTypeDisplayName",
    "types",
    "googleMapsUri",
    "businessStatus",
    "rating",
    "userRatingCount",
    "regularOpeningHours",
    "photos",
    "reviews",
)
_FIELD_MASK_BUSCA = ",".join(f"places.{c}" for c in _CAMPOS) + ",nextPageToken"
_FIELD_MASK_DETALHE = ",".join(_CAMPOS)
_FIELD_MASK_LOCAL = "places.location"
_FIELD_MASK_TESTE = "places.id"

_TIMEOUT_PADRAO = 12
_TAMANHO_PAGINA = 20  # máximo aceito pela API por página
_MAX_PAGINAS = 3  # a API entrega no máximo 60 resultados por consulta
_RAIO_MAXIMO = 50_000.0  # limite do locationBias.circle.radius (metros)


class ErroConfiguracao(Exception):
    """Levantada quando falta configuração essencial (ex.: chave de API)."""


def _cabecalhos(chave: str, field_mask: str) -> dict[str, str]:
    """Monta os cabeçalhos da Places API (a chave nunca é logada)."""
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": chave,
        "X-Goog-FieldMask": field_mask,
    }


def _exigir_chave(chave: str | None) -> str:
    """Valida a presença da chave de API."""
    chave = (chave or "").strip()
    if not chave:
        raise ErroConfiguracao(texto("prospeccao.google.erro_sem_chave"))
    return chave


def _tratar_erro_http(resp: requests.Response, contexto: str) -> None:
    """Traduz respostas de erro da API em exceções claras (sem vazar a chave)."""
    # Registra só o status (o corpo pode ecoar parâmetros da requisição).
    logger.warning("Places API retornou erro (%s): HTTP %s", contexto, resp.status_code)
    corpo = (resp.text or "")[:4000].upper()
    # 401/403 ou 400 com "API_KEY_INVALID"/"API key not valid": problema na chave.
    if resp.status_code in (401, 403) or "API_KEY" in corpo or "API KEY" in corpo:
        raise ErroConfiguracao(texto("prospeccao.google.erro_chave_invalida"))
    raise ErroConfiguracao(texto("prospeccao.google.erro_http", status=resp.status_code))


def _post(chave: str, field_mask: str, corpo: dict, timeout: float, contexto: str) -> dict:
    """POST no Text Search com tratamento uniforme de erros."""
    try:
        resp = requests.post(
            _URL_TEXT_SEARCH,
            headers=_cabecalhos(chave, field_mask),
            json=corpo,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.warning("Falha de rede na Places API (%s): %s", contexto, type(exc).__name__)
        raise ErroConfiguracao(texto("prospeccao.google.erro_rede")) from exc
    if not resp.ok:
        _tratar_erro_http(resp, contexto)
    try:
        return resp.json() or {}
    except ValueError:
        return {}


def _normalizar(place: dict) -> dict:
    """Converte um objeto ``place`` da API v1 no dict canônico do modulos."""
    local = place.get("location") or {}
    nome_exibicao = (place.get("displayName") or {}).get("text", "")
    categoria = (place.get("primaryTypeDisplayName") or {}).get("text", "")
    if not categoria:
        tipos = place.get("types") or []
        categoria = tipos[0] if tipos else ""

    dados = {
        "place_id": place.get("id", ""),
        "nome": nome_exibicao,
        "endereco": place.get("formattedAddress", ""),
        "telefone": place.get("nationalPhoneNumber")
        or place.get("internationalPhoneNumber", ""),
        "website": place.get("websiteUri", ""),
        "lat": local.get("latitude"),
        "lng": local.get("longitude"),
        "categoria": categoria,
    }
    # Métricas do motor de análise (nota, avaliações, fotos, horário, etc.).
    dados.update(extrair_sinais(place))
    return dados


def _centro_da_localizacao(chave: str, localizacao: str, timeout: float) -> dict | None:
    """Coordenadas da ``localizacao`` (texto) para o ``locationBias`` (best-effort)."""
    localizacao = (localizacao or "").strip()
    if not localizacao:
        return None
    try:
        dados = _post(
            chave,
            _FIELD_MASK_LOCAL,
            {"textQuery": localizacao, "pageSize": 1, "languageCode": "pt-BR", "regionCode": "BR"},
            timeout,
            "geolocalizacao",
        )
    except ErroConfiguracao:
        return None
    lugares = dados.get("places") or []
    local = (lugares[0].get("location") or {}) if lugares else {}
    if local.get("latitude") is None or local.get("longitude") is None:
        return None
    return {"latitude": local["latitude"], "longitude": local["longitude"]}


def buscar_empresas(
    chave: str,
    termo: str,
    localizacao: str,
    raio_metros: int,
    timeout: float = _TIMEOUT_PADRAO,
    max_paginas: int = _MAX_PAGINAS,
) -> list[dict]:
    """Busca estabelecimentos via Places Text Search (API v1), com paginação.

    A ``localizacao`` (texto livre, ex.: "Barra da Tijuca, Rio de Janeiro") é
    combinada ao ``termo`` na consulta textual. Quando a própria API encontra
    as coordenadas da localização, a busca recebe um ``locationBias`` circular
    com ``raio_metros`` (limitado a 50 km).

    Args:
        chave: chave da Google Places API (não é logada).
        termo: o que buscar (ex.: "restaurantes").
        localizacao: recorte geográfico em texto.
        raio_metros: raio desejado em metros.
        timeout: timeout de cada chamada em segundos.
        max_paginas: páginas de 20 resultados (máx. 3 = 60 resultados).

    Returns:
        Lista de dicts normalizados (ver módulo). Lista vazia se nada for achado.

    Raises:
        ErroConfiguracao: chave ausente/inválida, erro HTTP ou de rede.
    """
    chave = _exigir_chave(chave)

    consulta = " ".join(p for p in (termo, localizacao) if p).strip()
    corpo: dict[str, Any] = {
        "textQuery": consulta,
        "pageSize": _TAMANHO_PAGINA,
        "languageCode": "pt-BR",
        "regionCode": "BR",
    }
    centro = _centro_da_localizacao(chave, localizacao, timeout)
    if centro:
        raio = min(max(float(raio_metros or 0), 1.0), _RAIO_MAXIMO)
        corpo["locationBias"] = {"circle": {"center": centro, "radius": raio}}
    logger.info(
        "Places Text Search: termo=%r local=%r raio=%sm bias=%s",
        termo,
        localizacao,
        raio_metros,
        bool(centro),
    )

    resultados: list[dict] = []
    vistos: set[str] = set()
    token = None
    for _pagina in range(max(1, min(int(max_paginas), _MAX_PAGINAS))):
        if token:
            corpo["pageToken"] = token
        dados = _post(chave, _FIELD_MASK_BUSCA, corpo, timeout, "text-search")
        for place in dados.get("places") or []:
            normalizado = _normalizar(place)
            identificador = normalizado.get("place_id") or ""
            if identificador and identificador in vistos:
                continue
            vistos.add(identificador)
            resultados.append(normalizado)
        token = dados.get("nextPageToken")
        if not token:
            break

    logger.info("Places Text Search retornou %d resultado(s).", len(resultados))
    return resultados


def detalhes(
    chave: str,
    place_id: str,
    timeout: float = _TIMEOUT_PADRAO,
) -> dict | None:
    """Consulta detalhes de um ``place_id`` via Place Details (API v1).

    Returns:
        Dict normalizado, ou ``None`` se ``place_id`` for vazio.

    Raises:
        ErroConfiguracao: chave ausente/inválida, erro HTTP ou de rede.
    """
    chave = _exigir_chave(chave)
    place_id = (place_id or "").strip()
    if not place_id:
        return None

    # O recurso na API v1 é "places/{id}".
    url = f"{_BASE}/places/{place_id}"
    logger.info("Place Details: place_id=%s", place_id)

    try:
        resp = requests.get(
            url,
            headers=_cabecalhos(chave, _FIELD_MASK_DETALHE),
            params={"languageCode": "pt-BR", "regionCode": "BR"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.warning("Falha de rede em Place Details: %s", type(exc).__name__)
        raise ErroConfiguracao(texto("prospeccao.google.erro_rede")) from exc

    if not resp.ok:
        _tratar_erro_http(resp, "place-details")

    try:
        return _normalizar(resp.json() or {})
    except ValueError:
        return None


def testar_chave(chave: str, timeout: float = _TIMEOUT_PADRAO) -> bool:
    """Faz uma busca mínima (só ``places.id``) para validar a chave.

    Returns:
        ``True`` quando a API aceita a chave.

    Raises:
        ErroConfiguracao: chave ausente/inválida, erro HTTP ou de rede.
    """
    chave = _exigir_chave(chave)
    _post(
        chave,
        _FIELD_MASK_TESTE,
        {"textQuery": "padaria São Paulo", "pageSize": 1, "languageCode": "pt-BR", "regionCode": "BR"},
        timeout,
        "teste-de-chave",
    )
    return True

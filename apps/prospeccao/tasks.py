"""Tarefas do módulo de prospecção.

``executar_busca(busca_id)`` é síncrona, mas isolada e sem dependências de
request — pronta para virar uma task Celery (basta decorar). Ela:

1. marca a ``Busca`` como *executando*;
2. obtém a chave da Google Places API (conexão da busca, chave do Painel do
   módulo ou ``GOOGLE_MAPS_API_KEY``) e chama
   ``services.google_places.buscar_empresas``;
3. cria/atualiza as ``Empresa`` encontradas, já com as métricas do Places
   (nota, avaliações, fotos, horário, situação e última atividade);
4. para cada uma, chama ``services.orquestrador.analisar_empresa`` (site,
   motor de análise, diagnóstico e score);
5. atualiza ``total_resultados`` e o ``status`` final.

Cada etapa é protegida por ``try/except`` com ``logging`` — uma falha pontual
não derruba a execução inteira. Os serviços são importados DENTRO da função
para não pagar o custo de import no carregamento do módulo.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("modulos.prospeccao.tasks")

# Páginas de 20 resultados por busca. A execução é síncrona (dentro da
# requisição), por isso o padrão é 1 página (20 empresas) para não estourar o
# timeout do servidor. Ao migrar para Celery, pode subir até 3 (60 empresas).
PAGINAS_POR_BUSCA = 1

# Tamanhos máximos dos campos de texto da ``Empresa`` (evita erro no banco).
_LIMITES = {
    "nome": 255,
    "categoria": 150,
    "endereco": 255,
    "telefone": 50,
    "website": 300,
}


def _texto(valor: Any) -> str:
    """Normaliza um valor para texto enxuto (str vazia se ausente)."""
    if valor is None:
        return ""
    return str(valor).strip()


def _numero(valor: Any) -> float | None:
    """Converte para float quando possível; caso contrário, ``None``."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _mapear_place(place: dict) -> dict:
    """Mapeia um resultado de lugar (defensivo a diferentes nomes de chave).

    Cobre tanto chaves em PT-BR quanto os nomes crus da Places API, para não
    acoplar a task a uma forma específica do serviço ``google_places``.
    """
    if not isinstance(place, dict):
        return {}

    # Aceita tanto as chaves normalizadas do serviço ("lat"/"lng") quanto
    # variações comuns ("latitude"/"longitude") e o formato aninhado da API crua.
    latitude = _numero(place.get("lat"))
    if latitude is None:
        latitude = _numero(place.get("latitude"))
    longitude = _numero(place.get("lng"))
    if longitude is None:
        longitude = _numero(place.get("longitude"))
    geometria = place.get("geometry")
    if (latitude is None or longitude is None) and isinstance(geometria, dict):
        local = geometria.get("location")
        if isinstance(local, dict):
            latitude = latitude if latitude is not None else _numero(local.get("lat"))
            longitude = longitude if longitude is not None else _numero(local.get("lng"))

    categoria = _texto(place.get("categoria") or place.get("category"))
    if not categoria:
        tipos = place.get("types") or place.get("tipos")
        if isinstance(tipos, (list, tuple)) and tipos:
            categoria = _texto(tipos[0])

    dados = {
        "nome": _texto(place.get("nome") or place.get("name")),
        "categoria": categoria,
        "endereco": _texto(
            place.get("endereco")
            or place.get("formatted_address")
            or place.get("vicinity")
            or place.get("address")
        ),
        "telefone": _texto(
            place.get("telefone")
            or place.get("formatted_phone_number")
            or place.get("phone")
        ),
        "website": _texto(place.get("website") or place.get("site")),
        "latitude": latitude,
        "longitude": longitude,
    }
    for campo, limite in _LIMITES.items():
        dados[campo] = dados[campo][:limite]
    return dados


def _tem_metricas_places(place: dict) -> bool:
    """Indica se o resultado veio do serviço com as métricas do Places."""
    return isinstance(place, dict) and "situacao_horario" in place


def executar_busca(busca_id: int) -> dict:
    """Executa a busca ``busca_id`` de ponta a ponta (síncrono).

    Retorna um resumo: ``{"busca_id", "status", "total", "erros", "mensagem"}``
    (``mensagem`` explica falhas de configuração, como a falta da chave).
    Nunca levanta: todas as falhas são registradas e refletidas no ``status``.
    """
    from apps.prospeccao.models import Busca, Empresa
    from apps.prospeccao.services import credenciais

    resumo: dict[str, Any] = {
        "busca_id": busca_id,
        "status": "erro",
        "total": 0,
        "erros": 0,
        "mensagem": "",
    }

    try:
        busca = Busca.objects.select_related("conexao").get(pk=busca_id)
    except Busca.DoesNotExist:
        logger.error("Busca %s inexistente; execução abortada.", busca_id)
        return resumo

    busca.status = Busca.Status.EXECUTANDO
    try:
        busca.save(update_fields=["status"])
    except Exception:
        logger.exception("Falha ao marcar a busca %s como executando.", busca_id)

    conexao = busca.conexao
    chave = credenciais.chave_google(conexao)
    if not chave:
        from apps.nucleo.textos import texto

        logger.error("Busca %s sem chave de API válida; abortando.", busca_id)
        _finalizar(busca, Busca.Status.ERRO, 0)
        resumo["mensagem"] = texto("prospeccao.nova_busca.msg_sem_chave")
        return resumo

    # Etapa 1: buscar lugares (import tardio do serviço).
    try:
        from apps.prospeccao.services import google_places

        resultados = google_places.buscar_empresas(
            chave,
            busca.termo,
            busca.localizacao,
            busca.raio_metros,
            max_paginas=PAGINAS_POR_BUSCA,
        )
    except Exception as exc:
        logger.exception("Falha ao buscar empresas para a busca %s.", busca_id)
        _finalizar(busca, Busca.Status.ERRO, 0)
        if exc.__class__.__name__ == "ErroConfiguracao":
            resumo["mensagem"] = str(exc)
        return resumo

    if not resultados:
        logger.info("Busca %s não retornou resultados.", busca_id)
        _finalizar(busca, Busca.Status.CONCLUIDA, 0)
        resumo["status"] = "concluida"
        return resumo

    # Etapa 2: persistir e analisar cada empresa.
    processadas = 0
    erros = 0
    for place in resultados:
        try:
            empresa = _persistir_empresa(place, busca, Empresa)
            if empresa is None:
                continue
            processadas += 1
        except Exception:
            erros += 1
            logger.exception("Falha ao persistir empresa da busca %s.", busca_id)
            continue

        try:
            from apps.prospeccao.services import orquestrador

            orquestrador.analisar_empresa(empresa, conexao)
        except Exception:
            erros += 1
            logger.exception("Falha ao analisar a empresa %s (busca %s).", empresa.pk, busca_id)

    _finalizar(busca, Busca.Status.CONCLUIDA, processadas)
    resumo.update(status="concluida", total=processadas, erros=erros)
    logger.info(
        "Busca %s concluída: %d empresa(s), %d erro(s).", busca_id, processadas, erros
    )
    return resumo


def _persistir_empresa(place: dict, busca, modelo):
    """Cria ou atualiza uma ``Empresa`` a partir de um resultado de lugar."""
    dados = _mapear_place(place)
    nome = dados.get("nome")
    if not nome:
        return None

    place_id = _texto(place.get("place_id"))[:255] or None
    campos = {chave: valor for chave, valor in dados.items() if valor not in (None, "")}
    campos["busca"] = busca

    if _tem_metricas_places(place):
        from apps.prospeccao.services import orquestrador

        # O perfil do Google é a fonte da verdade do site ("websiteUri" nulo).
        campos["website"] = dados.get("website", "")
        campos.update(orquestrador.campos_places(place))

    if place_id:
        empresa, _criada = modelo.objects.update_or_create(
            place_id=place_id, defaults=campos
        )
    else:
        # Sem place_id não há como deduplicar com segurança: cria um novo registro.
        empresa = modelo.objects.create(**campos)
    return empresa


def _finalizar(busca, status: str, total: int) -> None:
    """Grava o status final e o total de resultados da busca."""
    busca.status = status
    busca.total_resultados = total
    try:
        busca.save(update_fields=["status", "total_resultados"])
    except Exception:
        logger.exception("Falha ao finalizar a busca %s.", getattr(busca, "pk", "?"))

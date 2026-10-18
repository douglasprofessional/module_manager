"""Recuperação das credenciais usadas pelo módulo de prospecção.

Ordem de prioridade da chave da Google Places API (New):

1. a ``ConexaoGoogle`` escolhida na busca (se ativa e com chave);
2. a chave colada e salva no **Painel do módulo** (``ConfiguracaoProspeccao``);
3. a variável de ambiente ``GOOGLE_MAPS_API_KEY`` (fallback legado).

Nenhuma função aqui registra chaves em log.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:  # apenas para type hints
    from apps.prospeccao.models import ConexaoGoogle

ORIGEM_CONEXAO = "conexao"
ORIGEM_PAINEL = "painel"
ORIGEM_AMBIENTE = "ambiente"


def _chave_ambiente() -> str:
    return (getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()


def chave_google(conexao: "ConexaoGoogle | None" = None) -> str:
    """Retorna a chave da Google Places API a usar (string vazia se nenhuma)."""
    if conexao is not None and getattr(conexao, "ativo", False):
        chave = (conexao.chave_api or "").strip()
        if chave:
            return chave

    from apps.prospeccao.models import ConfiguracaoProspeccao

    chave = (ConfiguracaoProspeccao.obter().chave_google or "").strip()
    if chave:
        return chave
    return _chave_ambiente()


def origem_chave_google() -> str:
    """De onde vem a chave padrão (sem conexão): ``painel``, ``ambiente`` ou ``""``."""
    from apps.prospeccao.models import ConfiguracaoProspeccao

    if ConfiguracaoProspeccao.obter().tem_chave_google:
        return ORIGEM_PAINEL
    if _chave_ambiente():
        return ORIGEM_AMBIENTE
    return ""

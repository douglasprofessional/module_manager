"""Registro do módulo Kanban no núcleo (adendo docs/SPEC_MODULOS.md — MÓDULO 1).

Define ``ModuloKanban`` (subclasse de ``ModuloBase``) e a registra no ``registro``
singleton. Fornece:

- ``itens_menu``: o item de sidebar "Kanban".
- ``cards_resumo``: 3 KPIs (quadros, tarefas em andamento, tarefas atrasadas) no
  formato EXATO da seção de regras comuns do adendo.
- ``contexto_dashboard``: ``{}`` (o painel principal é da prospecção).

É resiliente: qualquer falha em ``cards_resumo`` resulta em lista vazia,
mantendo o dashboard funcional.
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.kanban.modulo")


@registro.registrar
class ModuloKanban(ModuloBase):
    """Módulo Kanban: quadros, colunas e cartões de tarefas."""

    slug = "kanban"
    nome = texto("modulos.kanban.nome")
    icone = "kanban"
    ordem = 20
    descricao = texto("modulos.kanban.descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para a lista de quadros."""
        return "kanban:lista"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        rotas_ativas = {"kanban:lista", "kanban:quadro", "kanban:novo_quadro"}
        return [
            {
                "rotulo": texto("modulos.kanban.menu.kanban"),
                "url": self._url_ou_hash("kanban:lista"),
                "icone": "kanban",
                "ativo": rota_atual in rotas_ativas,
            }
        ]

    def contexto_dashboard(self, request) -> dict:
        """O Kanban não injeta dados no painel principal (seção 7)."""
        return {}

    def cards_resumo(self, request) -> list[dict]:
        """KPIs do Kanban para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from apps.kanban.models import Cartao, Quadro

            hoje = timezone.localdate()
            quadros = Quadro.objects.filter(arquivado=False).count()
            # Só conta cartões de quadros ativos (alinha os KPIs com a lista de
            # quadros, que oculta os arquivados).
            cartoes_ativos = Cartao.objects.filter(coluna__quadro__arquivado=False)
            em_andamento = cartoes_ativos.filter(concluido=False).count()
            atrasadas = cartoes_ativos.filter(
                concluido=False, prazo__lt=hoje
            ).count()
            url_lista = self._url_ou_hash("kanban:lista")
            return [
                {
                    "rotulo": texto("modulos.kanban.cards.quadros_rotulo"),
                    "valor": quadros,
                    "detalhe": texto("modulos.kanban.cards.quadros_detalhe"),
                    "icone": "kanban",
                    "cor": "#7c5cff",
                    "url": url_lista,
                },
                {
                    "rotulo": texto("modulos.kanban.cards.andamento_rotulo"),
                    "valor": em_andamento,
                    "detalhe": texto("modulos.kanban.cards.andamento_detalhe"),
                    "icone": "tarefa",
                    "cor": "#38bdf8",
                    "url": url_lista,
                },
                {
                    "rotulo": texto("modulos.kanban.cards.atrasadas_rotulo"),
                    "valor": atrasadas,
                    "detalhe": texto("modulos.kanban.cards.atrasadas_detalhe"),
                    "icone": "alerta",
                    "cor": "#f87171",
                    "url": url_lista,
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo do Kanban.")
            return []

    # -- Auxiliares de menu -------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            logger.debug("URL '%s' não pôde ser resolvida.", nome_url)
            return "#"

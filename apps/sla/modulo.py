"""Registro do módulo de SLA no núcleo (adendo docs/SPEC_MODULOS.md — MÓDULO 2).

Define ``ModuloSLA`` (subclasse de ``ModuloBase``) e a registra no ``registro``
singleton. Fornece:

- ``itens_menu``: itens de sidebar do módulo (Chamados e Políticas).
- ``cards_resumo``: 4 KPIs (abertos, em risco, estourado, % no prazo) calculados
  em Python sobre um queryset enxuto (``select_related("politica")``) para evitar
  N+1. Qualquer falha resulta em ``[]`` (o dashboard nunca quebra por um módulo).
- ``contexto_dashboard``: ``{}`` (o painel principal é da prospecção).
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.sla.modulo")


@registro.registrar
class ModuloSLA(ModuloBase):
    """Módulo de SLA: chamados regidos por políticas de prazo."""

    slug = "sla"
    nome = texto("modulos.sla.nome")
    icone = "sla"
    ordem = 30
    descricao = texto("modulos.sla.descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para a lista de chamados."""
        return "sla:lista"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        definicoes = [
            (
                texto("modulos.sla.menu.chamados"),
                "sla:lista",
                "sla",
                {
                    "sla:lista",
                    "sla:detalhe",
                    "sla:novo_chamado",
                    "sla:registrar_resposta",
                    "sla:resolver",
                },
            ),
            (texto("modulos.sla.menu.politicas"), "sla:politicas", "config", {"sla:politicas"}),
        ]
        itens: list[dict] = []
        for rotulo, nome_url, icone, rotas_ativas in definicoes:
            itens.append(
                {
                    "rotulo": rotulo,
                    "url": self._url_ou_hash(nome_url),
                    "icone": icone,
                    "ativo": rota_atual in rotas_ativas,
                }
            )
        return itens

    def contexto_dashboard(self, request) -> dict:
        """O painel principal é da prospecção; o SLA não injeta contexto."""
        return {}

    def cards_resumo(self, request) -> list[dict]:
        """4 KPIs de SLA para a faixa de resumo do dashboard.

        Itera uma única vez sobre um queryset enxuto (``select_related`` na
        política) e calcula as situações em Python. Resiliente: qualquer falha
        resulta em lista vazia.
        """
        try:
            from apps.sla.models import Chamado

            chamados = list(Chamado.objects.select_related("politica").all())

            abertos = 0
            em_risco = 0
            estourado = 0
            resolvidos = 0
            no_prazo = 0
            status_abertos = set(Chamado.STATUS_ABERTOS)

            for chamado in chamados:
                situacao = chamado.situacao_resolucao()
                if chamado.status in status_abertos:
                    abertos += 1
                    if situacao == "em_risco":
                        em_risco += 1
                if situacao == "estourado":
                    estourado += 1
                if chamado.resolvido_em is not None:
                    resolvidos += 1
                    if situacao == "cumprido":
                        no_prazo += 1

            pct_no_prazo = round(no_prazo / resolvidos * 100) if resolvidos else 0

            url = self._url_ou_hash("sla:lista")
            return [
                {
                    "rotulo": texto("modulos.sla.cards.abertos_rotulo"),
                    "valor": abertos,
                    "detalhe": texto("modulos.sla.cards.abertos_detalhe"),
                    "icone": "sla",
                    "cor": "#7c5cff",
                    "url": url,
                },
                {
                    "rotulo": texto("modulos.sla.cards.risco_rotulo"),
                    "valor": em_risco,
                    "detalhe": texto("modulos.sla.cards.risco_detalhe"),
                    "icone": "alerta",
                    "cor": "#fbbf24",
                    "url": url,
                },
                {
                    "rotulo": texto("modulos.sla.cards.estourado_rotulo"),
                    "valor": estourado,
                    "detalhe": texto("modulos.sla.cards.estourado_detalhe"),
                    "icone": "alerta",
                    "cor": "#f87171",
                    "url": url,
                },
                {
                    "rotulo": texto("modulos.sla.cards.no_prazo_rotulo"),
                    "valor": f"{pct_no_prazo}%",
                    "detalhe": texto("modulos.sla.cards.no_prazo_detalhe"),
                    "icone": "tarefa",
                    "cor": "#34d399",
                    "url": url,
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo do SLA.")
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

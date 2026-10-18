"""Registro do módulo de Monitoramento no núcleo (adendo 2 — MÓDULO 3).

Define ``ModuloMonitoramento`` (subclasse de ``ModuloBase``) e a registra no
``registro`` singleton. Fornece:

- ``itens_menu``: o item de sidebar "Servidores".
- ``cards_resumo``: 3 KPIs (Servidores / Online / Offline-Erro) a partir do banco.
- ``contexto_dashboard``: ``{}`` (o painel principal é da prospecção).
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.monitoramento.modulo")


@registro.registrar
class ModuloMonitoramento(ModuloBase):
    """Módulo de monitoramento de VPSs (painel estilo Proxmox via SSH)."""

    slug = "monitoramento"
    nome = texto("modulos.monitoramento.nome")
    icone = "servidor"
    ordem = 40
    descricao = texto("modulos.monitoramento.descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para a lista de servidores."""
        return "monitoramento:lista"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        rotas_servidores = {
            "monitoramento:lista",
            "monitoramento:detalhe",
            "monitoramento:novo",
            "monitoramento:editar",
        }
        return [
            {
                "rotulo": texto("modulos.monitoramento.menu.servidores"),
                "url": self._url_ou_hash("monitoramento:lista"),
                "icone": "servidor",
                "ativo": rota_atual in rotas_servidores,
            }
        ]

    def cards_resumo(self, request) -> list[dict]:
        """KPIs do monitoramento para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from apps.monitoramento.models import ServidorVPS

            # Todos os KPIs consideram apenas servidores ativos, para manter a
            # coerência (o card "Servidores" conta ativos; a coleta em massa só
            # roda em ativos). Assim "Online" nunca supera "Servidores".
            base = ServidorVPS.objects.filter(ativo=True)
            servidores = base.count()
            online = base.filter(ultimo_status=ServidorVPS.Status.ONLINE).count()
            offline_erro = base.filter(
                ultimo_status__in=[
                    ServidorVPS.Status.OFFLINE,
                    ServidorVPS.Status.ERRO,
                ]
            ).count()
            url_lista = self._url_ou_hash("monitoramento:lista")
            return [
                {
                    "rotulo": texto("modulos.monitoramento.cards.servidores_rotulo"),
                    "valor": servidores,
                    "detalhe": texto("modulos.monitoramento.cards.servidores_detalhe"),
                    "icone": "servidor",
                    "cor": "#7c5cff",
                    "url": url_lista,
                },
                {
                    "rotulo": texto("modulos.monitoramento.cards.online_rotulo"),
                    "valor": online,
                    "detalhe": texto("modulos.monitoramento.cards.online_detalhe"),
                    "icone": "atualizar",
                    "cor": "#34d399",
                    "url": url_lista,
                },
                {
                    "rotulo": texto("modulos.monitoramento.cards.offline_rotulo"),
                    "valor": offline_erro,
                    "detalhe": texto("modulos.monitoramento.cards.offline_detalhe"),
                    "icone": "alerta",
                    "cor": "#f87171",
                    "url": url_lista,
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo do monitoramento.")
            return []

    def contexto_dashboard(self, request) -> dict:
        """O painel principal é da prospecção; este módulo não injeta dados."""
        return {}

    # -- Auxiliares ---------------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            logger.debug("URL '%s' não pôde ser resolvida.", nome_url)
            return "#"

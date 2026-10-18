"""Registro do modulo de Cupons no nucleo.

Define ``ModuloCupons`` (subclasse de ``ModuloBase``) e a registra no ``registro``
singleton. Fornece:

- ``itens_menu``: os itens de sidebar "Cupons", "Clientes" e "Cobrancas".
- ``cards_resumo``: 4 KPIs a partir de ``services.dashboard_metrics(hoje)``, no
  formato EXATO das regras comuns (rotulo/valor/detalhe/icone/cor/url).
- ``contexto_dashboard``: ``{}`` (o painel principal do dashboard e do nucleo;
  o painel proprio do modulo e a view ``cupons:painel``).
- ``excluir_dados``: apaga TODOS os registros do modulo (na ordem correta).

Tudo e resiliente: qualquer falha em ``cards_resumo`` resulta em lista vazia,
mantendo o dashboard funcional. O icone "financeiro" nao existe na biblioteca de
icones do sistema; usamos o fallback existente "tarefa".
"""

from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.cupons.modulo")


@registro.registrar
class ModuloCupons(ModuloBase):
    """Modulo de Cupons: clientes, cupons de desconto e cobrancas mensais."""

    slug = "cupons"
    nome = texto("modulos.cupons.nome")
    icone = "cupom"
    ordem = 40
    descricao = texto("modulos.cupons.descricao")

    def url_inicial(self) -> str:
        """Item principal do modulo aponta para o painel de cupons."""
        return "cupons:painel"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do modulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        definicoes = [
            (
                texto("modulos.cupons.menu.cupons"),
                "cupons:list",
                "cupom",
                {"cupons:list", "cupons:create", "cupons:update", "cupons:delete"},
            ),
            (
                texto("modulos.cupons.menu.clientes"),
                "cupons:cliente_lista",
                "grupo",
                {
                    "cupons:painel",
                    "cupons:cliente_lista",
                    "cupons:customer_create",
                    "cupons:customer_detail",
                    "cupons:customer_update",
                },
            ),
            (
                texto("modulos.cupons.menu.cobrancas"),
                "cupons:charge_list",
                # "financeiro" nao existe na biblioteca de icones: usamos "tarefa".
                "tarefa",
                {"cupons:charge_list", "cupons:charge_edit"},
            ),
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
        """O painel principal do dashboard e do nucleo; este modulo nao injeta dados."""
        return {}

    def cards_resumo(self, request) -> list[dict]:
        """4 KPIs de Cupons para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from apps.cupons.services import dashboard_metrics

            hoje = timezone.localdate()
            metricas = dashboard_metrics(hoje) or {}
            clientes = metricas.get("clientes", {}) or {}

            return [
                {
                    "rotulo": texto("modulos.cupons.cards.cupons_rotulo"),
                    "valor": metricas.get("cupons_ativos", 0),
                    "detalhe": texto("modulos.cupons.cards.cupons_detalhe"),
                    "icone": "cupom",
                    "cor": "#7c5cff",
                    "url": self._url_ou_hash("cupons:list"),
                },
                {
                    "rotulo": texto("modulos.cupons.cards.clientes_rotulo"),
                    "valor": clientes.get("ativos", 0),
                    "detalhe": texto("modulos.cupons.cards.clientes_detalhe"),
                    "icone": "grupo",
                    "cor": "#34d399",
                    "url": self._url_ou_hash("cupons:cliente_lista"),
                },
                {
                    "rotulo": texto("modulos.cupons.cards.aniversariantes_rotulo"),
                    "valor": clientes.get("aniversariantes", 0),
                    "detalhe": texto("modulos.cupons.cards.aniversariantes_detalhe"),
                    "icone": "calendario",
                    "cor": "#fbbf24",
                    "url": self._url_ou_hash("cupons:painel"),
                },
                {
                    "rotulo": texto("modulos.cupons.cards.cobrancas_rotulo"),
                    "valor": metricas.get("cobrancas_em_aberto", 0),
                    "detalhe": texto("modulos.cupons.cards.cobrancas_detalhe"),
                    "icone": "tarefa",
                    "cor": "#f87171",
                    "url": self._url_ou_hash("cupons:charge_list"),
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um modulo
            logger.exception("Falha ao montar cards_resumo do modulo de Cupons.")
            return []

    def excluir_dados(self, request) -> int:
        """Apaga TODOS os dados do modulo e retorna a contagem total removida.

        Ordem de exclusao (respeita as FKs): cobrancas -> aplicacoes -> cupons ->
        clientes. A exclusao em cascata do banco tambem cobriria aplicacoes e
        cobrancas ao remover clientes/cupons, mas contamos cada modelo
        explicitamente para reportar o total ao painel de Configuracoes.
        """
        from apps.cupons.models import (
            Coupon,
            CouponAssignment,
            Customer,
            MonthlyCharge,
        )

        total = 0
        for modelo in (MonthlyCharge, CouponAssignment, Coupon, Customer):
            removidos, _detalhe = modelo.objects.all().delete()
            total += removidos
        return total

    # -- Auxiliares de menu -------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            logger.debug("URL '%s' nao pode ser resolvida.", nome_url)
            return "#"

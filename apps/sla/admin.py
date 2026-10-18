"""Admin do módulo de SLA.

``Politica`` e ``Chamado`` recebem ``list_display`` úteis para operação
(status, prioridade, prazos e responsável). Os prazos calculados são somente
leitura no formulário do chamado.
"""
from __future__ import annotations

from django.contrib import admin

from apps.sla.models import Chamado, Politica


@admin.register(Politica)
class PoliticaAdmin(admin.ModelAdmin):
    """Admin de políticas de SLA."""

    list_display = (
        "nome",
        "prazo_resposta_horas",
        "prazo_resolucao_horas",
        "ativo",
        "criado_em",
    )
    list_filter = ("ativo", "criado_em")
    search_fields = ("nome", "descricao")
    readonly_fields = ("criado_em",)


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    """Admin de chamados: visão operacional de status, prioridade e prazos."""

    list_display = (
        "titulo",
        "politica",
        "prioridade",
        "status",
        "responsavel",
        "aberto_em",
        "prazo_resolucao",
        "resolvido_em",
    )
    list_filter = ("status", "prioridade", "politica", "aberto_em")
    search_fields = ("titulo", "descricao", "solicitante")
    readonly_fields = (
        "prazo_resposta",
        "prazo_resolucao",
        "criado_em",
        "atualizado_em",
    )
    list_select_related = ("politica", "responsavel")
    autocomplete_fields = ("responsavel",)
    date_hierarchy = "aberto_em"
    ordering = ("-aberto_em",)

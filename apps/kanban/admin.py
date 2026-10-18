"""Admin do módulo Kanban.

Expõe ``Quadro`` (com colunas em inline), ``Coluna`` e ``Cartao`` com
``list_display`` úteis para operação. Sem segredos envolvidos.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.kanban.models import Cartao, Coluna, Quadro


class ColunaInline(admin.TabularInline):
    """Colunas editáveis diretamente na página do quadro."""

    model = Coluna
    extra = 1
    fields = ("nome", "ordem", "limite_wip", "cor")
    ordering = ("ordem", "id")


@admin.register(Quadro)
class QuadroAdmin(admin.ModelAdmin):
    """Admin de quadros, com as colunas em inline."""

    list_display = ("nome", "arquivado", "criado_por", "criado_em", "atualizado_em")
    list_filter = ("arquivado", "criado_em")
    search_fields = ("nome", "descricao")
    readonly_fields = ("criado_em", "atualizado_em")
    inlines = (ColunaInline,)


@admin.register(Coluna)
class ColunaAdmin(admin.ModelAdmin):
    """Admin de colunas: ordem, WIP e uso corrente."""

    list_display = ("nome", "quadro", "ordem", "limite_wip", "em_wip", "estourou_wip")
    list_filter = ("quadro",)
    search_fields = ("nome", "quadro__nome")
    list_select_related = ("quadro",)
    ordering = ("quadro", "ordem", "id")

    @admin.display(description=_("cartões"))
    def em_wip(self, obj: Coluna) -> int:
        return obj.em_wip()

    @admin.display(boolean=True, description=_("estourou WIP"))
    def estourou_wip(self, obj: Coluna) -> bool:
        return obj.estourou_wip


@admin.register(Cartao)
class CartaoAdmin(admin.ModelAdmin):
    """Admin de cartões: visão operacional de tarefas."""

    list_display = (
        "titulo",
        "coluna",
        "prioridade",
        "responsavel",
        "prazo",
        "concluido",
        "atrasado",
        "criado_em",
    )
    list_filter = ("prioridade", "concluido", "coluna__quadro", "prazo")
    search_fields = ("titulo", "descricao", "coluna__nome", "coluna__quadro__nome")
    readonly_fields = ("criado_em", "atualizado_em")
    list_select_related = ("coluna", "coluna__quadro", "responsavel")
    autocomplete_fields = ("coluna", "responsavel")
    ordering = ("coluna", "ordem", "id")

    @admin.display(boolean=True, description=_("atrasado"))
    def atrasado(self, obj: Cartao) -> bool:
        return obj.atrasado()

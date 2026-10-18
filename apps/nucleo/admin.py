"""Admin do núcleo.

Registra ``RegistroAuditoria`` em modo SOMENTE-LEITURA: a trilha de auditoria
não pode ser criada, editada ou apagada pela interface (apenas consultada).
"""
from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Exibição somente-leitura da trilha de auditoria."""

    list_display = ("quando", "usuario", "acao", "objeto_repr", "ip")
    list_filter = ("acao", "quando")
    search_fields = ("acao", "objeto_repr", "ip", "usuario__email")
    date_hierarchy = "quando"
    ordering = ("-quando",)
    readonly_fields = ("usuario", "acao", "objeto_repr", "ip", "quando")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        # Retornar False mantém a visualização (detalhe) em modo leitura.
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

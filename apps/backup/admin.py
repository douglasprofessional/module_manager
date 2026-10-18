"""Admin do módulo de backup.

Os campos gerados pelo sistema (``arquivo``, ``checksum_sha256``,
``tamanho_bytes``) e os carimbos de tempo são somente-leitura: são produzidos
pelo serviço, não editados à mão. Nenhum segredo é exibido (o modelo não guarda
segredos).
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.backup.models import Backup


@admin.register(Backup)
class BackupAdmin(admin.ModelAdmin):
    """Admin de backups: visão operacional dos artefatos gerados."""

    list_display = ("criado_em", "tipo", "escopo", "status", "tamanho")
    list_filter = ("tipo", "status", "criado_em")
    search_fields = ("rotulo", "escopo", "arquivo")
    readonly_fields = (
        "arquivo",
        "checksum_sha256",
        "tamanho_bytes",
        "criado_em",
        "concluido_em",
    )
    ordering = ("-criado_em",)

    @admin.display(description=_("tamanho"))
    def tamanho(self, obj: Backup) -> str:
        return obj.tamanho_texto()

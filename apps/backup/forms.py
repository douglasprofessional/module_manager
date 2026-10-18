"""Formulário do módulo de backup (adendo 2 — MÓDULO 4).

``BackupForm`` coleta o ``tipo`` (módulo/completo), o ``escopo`` (app_label,
escolhido de ``modulos_disponiveis()`` — a ALLOWLIST) e ``incluir_media``.

A validação garante que, quando o tipo é ``modulo``, o escopo esteja de fato na
allowlist (defesa em profundidade — o serviço também revalida). O ``tipo`` usa
``RadioSelect`` para permitir um toggle CSS puro (sem JS inline, respeitando a
CSP ``script-src 'self'``) que mostra/oculta os campos conforme a escolha.
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.backup.models import Backup
from apps.backup.services import backup_service


class BackupForm(forms.Form):
    """Escolhe o tipo, o escopo (quando módulo) e se inclui a mídia."""

    tipo = forms.ChoiceField(
        label=_("Tipo de backup"),
        choices=Backup.Tipo.choices,
        initial=Backup.Tipo.MODULO,
        widget=forms.RadioSelect,
    )
    escopo = forms.ChoiceField(
        label=_("Módulo"),
        required=False,
        widget=forms.Select(attrs={"class": "campo__entrada campo__entrada--select"}),
    )
    incluir_media = forms.BooleanField(
        label=_("Incluir mídia (uploads em MEDIA_ROOT)"),
        required=False,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        opcoes = backup_service.modulos_disponiveis()
        self.fields["escopo"].choices = [("", _("Selecione um módulo"))] + list(opcoes)

    def clean(self) -> dict:
        """Valida a coerência entre tipo e escopo (allowlist)."""
        dados = super().clean()
        tipo = dados.get("tipo")
        escopo = (dados.get("escopo") or "").strip()

        if tipo == Backup.Tipo.MODULO:
            allowlist = {app_label for app_label, _rotulo in backup_service.modulos_disponiveis()}
            if not escopo or escopo not in allowlist:
                self.add_error(
                    "escopo",
                    forms.ValidationError(
                        _("Selecione um módulo válido para o backup."),
                        code="escopo_invalido",
                    ),
                )
        return dados

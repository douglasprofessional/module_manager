"""Configuração do app de autenticação 'contas'."""
from __future__ import annotations

from django.apps import AppConfig


class ContasConfig(AppConfig):
    """AppConfig do app de contas (login por e-mail, somente administradores)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contas"
    # label derivado automaticamente -> "contas" (usado em AUTH_USER_MODEL="contas.Usuario")
    verbose_name = "Contas"

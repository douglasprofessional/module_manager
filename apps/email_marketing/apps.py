"""Configuração do app 'email_marketing' (módulo plugável — Marketing por E-mail).

Ao ficar pronto (``ready()``), importa ``apps.email_marketing.modulo`` para que a
classe ``ModuloEmailMarketing`` se registre no ``registro`` do núcleo. É a mesma
inversão de dependência dos demais módulos: o núcleo nunca importa este app; é
este app que se anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.email_marketing.apps")


class EmailMarketingConfig(AppConfig):
    """AppConfig do módulo de marketing por e-mail (label implícito: ``email_marketing``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.email_marketing"
    verbose_name = "Marketing por E-mail"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.email_marketing import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo de marketing por e-mail no núcleo.")

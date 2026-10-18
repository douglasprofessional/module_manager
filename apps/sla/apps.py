"""Configuração do app 'sla' (módulo plugável de SLA / chamados).

Ao ficar pronto (``ready()``), importa ``apps.sla.modulo`` para que a classe
``ModuloSLA`` se registre no ``registro`` do núcleo. É a inversão de dependência
descrita na seção 6 da SPEC: o núcleo nunca importa este app; é este app que se
anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.sla.apps")


class SlaConfig(AppConfig):
    """AppConfig do módulo de SLA (label implícito: ``sla``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sla"
    verbose_name = "SLA"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.sla import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo de SLA no núcleo.")

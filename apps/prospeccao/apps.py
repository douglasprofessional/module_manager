"""Configuração do app 'prospeccao' (1º módulo plugável).

Ao ficar pronto (``ready()``), importa ``apps.prospeccao.modulo`` para que a
classe ``ModuloProspeccao`` se registre no ``registro`` do núcleo. É a inversão
de dependência descrita na seção 6 da SPEC: o núcleo nunca importa este app; é
este app que se anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.prospeccao.apps")


class ProspeccaoConfig(AppConfig):
    """AppConfig do módulo de prospecção (label implícito: ``prospeccao``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.prospeccao"
    verbose_name = "Prospecção"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.prospeccao import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo de prospecção no núcleo.")

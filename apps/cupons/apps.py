"""Configuracao do app 'cupons' (modulo plugavel de cupons/clientes/cobrancas).

Ao ficar pronto (``ready()``), importa ``apps.cupons.signals`` (invalidacao de
cache) e ``apps.cupons.modulo`` (registro no nucleo). Cada import fica em seu
proprio ``try/except`` com logging para nunca impedir o boot por falha de um
efeito colateral (mesmo padrao do ``apps.kanban``).
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.cupons.apps")


class CuponsConfig(AppConfig):
    """AppConfig do modulo de Cupons (label implicito: ``cupons``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cupons"
    verbose_name = "Cupons"

    def ready(self) -> None:
        """Liga os signals e registra o modulo no nucleo."""
        try:
            from apps.cupons import signals  # noqa: F401  (efeito colateral: signals)
        except Exception:  # pragma: no cover - nao impedir o boot por falha de signals
            logger.exception("Falha ao registrar os signals do modulo de Cupons.")

        try:
            from apps.cupons import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - nao impedir o boot por falha de registro
            logger.exception("Falha ao registrar o modulo de Cupons no nucleo.")

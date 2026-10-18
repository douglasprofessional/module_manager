"""Configuração do app 'monitoramento' (módulo plugável — VPS estilo Proxmox).

Ao ficar pronto (``ready()``), importa ``apps.monitoramento.modulo`` para que a
classe ``ModuloMonitoramento`` se registre no ``registro`` do núcleo. É a mesma
inversão de dependência dos demais módulos: o núcleo nunca importa este app; é
este app que se anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.monitoramento.apps")


class MonitoramentoConfig(AppConfig):
    """AppConfig do módulo de monitoramento (label implícito: ``monitoramento``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.monitoramento"
    verbose_name = "Monitoramento"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.monitoramento import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo de monitoramento no núcleo.")

"""Configuração do app 'backup' (módulo plugável de backups).

Ao ficar pronto (``ready()``), importa ``apps.backup.modulo`` para que a classe
``ModuloBackup`` se registre no ``registro`` do núcleo. É a mesma inversão de
dependência dos demais módulos (seção 6 da SPEC): o núcleo nunca importa este
app; é este app que se anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.backup.apps")


class BackupConfig(AppConfig):
    """AppConfig do módulo de backup (label implícito: ``backup``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backup"
    verbose_name = "Backup"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.backup import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo de backup no núcleo.")

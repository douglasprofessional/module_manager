"""Configuração do app 'kanban' (módulo plugável de quadros de tarefas).

Ao ficar pronto (``ready()``), importa ``apps.kanban.modulo`` para que a classe
``ModuloKanban`` se registre no ``registro`` do núcleo. É a mesma inversão de
dependência de ``apps.prospeccao`` (seção 6 da SPEC): o núcleo nunca importa este
app; é este app que se anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.kanban.apps")


class KanbanConfig(AppConfig):
    """AppConfig do módulo Kanban (label implícito: ``kanban``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kanban"
    verbose_name = "Kanban"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.kanban import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo Kanban no núcleo.")

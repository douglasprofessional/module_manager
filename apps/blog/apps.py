"""Configuração do app 'blog' (módulo plugável de conteúdo + validação SEO).

Ao ficar pronto (``ready()``), importa ``apps.blog.modulo`` para que a classe
``ModuloBlog`` se registre no ``registro`` do núcleo. É a mesma inversão de
dependência dos demais módulos (seção 6 da SPEC): o núcleo nunca importa este
app; é este app que se anuncia ao núcleo.
"""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.blog.apps")


class BlogConfig(AppConfig):
    """AppConfig do módulo Blog (label implícito: ``blog``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.blog"
    verbose_name = "Blog"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.blog import modulo  # noqa: F401  (efeito colateral: registro)
        except Exception:  # pragma: no cover - não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo Blog no núcleo.")

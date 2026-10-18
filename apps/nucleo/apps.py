"""Configuração do app 'nucleo'.

O núcleo é a BASE do sistema e não conhece os módulos: ele apenas oferece o
``registro`` (ponto de extensão). A descoberta é feita pelos próprios
apps-módulo no ``ready()`` de cada um — por isso este AppConfig não importa
nada de outros apps.
"""
from __future__ import annotations

from django.apps import AppConfig


class NucleoConfig(AppConfig):
    """AppConfig do núcleo (label implícito: ``nucleo``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.nucleo"
    verbose_name = "Núcleo"

"""Habilita todos os módulos registrados (apenas para DEMONSTRAÇÃO).

Em produção, os módulos começam DESLIGADOS por padrão (o administrador habilita
em Configurações). Este comando existe só para o ambiente de demonstração
(``SEED_DEMO=1``), para que a demo já mostre os módulos no menu e no dashboard.
É idempotente.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Habilita todos os módulos registrados (uso em demonstração)."

    def handle(self, *args, **opcoes) -> None:
        from apps.nucleo.models import ModuloEstado
        from apps.nucleo.modulos import registro

        habilitados = 0
        for modulo in registro.todos():
            slug = getattr(modulo, "slug", "")
            if not slug:
                continue
            ModuloEstado.definir(slug, True)
            habilitados += 1

        self.stdout.write(
            self.style.SUCCESS(f"{habilitados} módulo(s) habilitado(s) para a demonstração.")
        )

"""
Marca cobrancas vencidas como "Em atraso" e atualiza a situacao dos clientes.

Uso:
    python manage.py sincronizar_inadimplencia
"""

from django.core.management.base import BaseCommand

from apps.cupons.services import sync_delinquency


class Command(BaseCommand):
    help = "Sincroniza a inadimplencia com base nas cobrancas vencidas."

    def handle(self, *args, **options):
        resultado = sync_delinquency()
        self.stdout.write(
            self.style.SUCCESS(
                "{vencidas} cobranca(s) marcada(s) como em atraso, {marcados} cliente(s) "
                "inadimplente(s), {liberados} liberado(s).".format(**resultado)
            )
        )

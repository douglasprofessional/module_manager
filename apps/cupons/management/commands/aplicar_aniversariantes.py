"""
Aplica o cupom automatico de aniversario para o mes informado.

Uso:
    python manage.py aplicar_aniversariantes            # mes atual
    python manage.py aplicar_aniversariantes --mes 2026-09
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cupons.dates import month_label, parse_month
from apps.cupons.services import ensure_birthday_assignments


class Command(BaseCommand):
    help = "Concede o cupom de aniversario aos clientes ativos do mes."

    def add_arguments(self, parser):
        parser.add_argument("--mes", default=None, help="Mes no formato AAAA-MM (padrao: atual).")

    def handle(self, *args, **options):
        referencia = parse_month(options["mes"], timezone.localdate())
        criadas = ensure_birthday_assignments(referencia, force=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"{criadas} aplicacao(oes) de aniversario criada(s) em {month_label(referencia)}."
            )
        )

"""
Gera (ou atualiza) as cobrancas mensais de todos os clientes ativos.

Uso:
    python manage.py gerar_cobrancas
    python manage.py gerar_cobrancas --mes 2026-09
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cupons.dates import month_label, parse_month
from apps.cupons.services import generate_charges, sync_delinquency


class Command(BaseCommand):
    help = "Gera as cobrancas do mes (mensalidade menos cupons aplicados)."

    def add_arguments(self, parser):
        parser.add_argument("--mes", default=None, help="Mes no formato AAAA-MM (padrao: atual).")
        parser.add_argument(
            "--sem-inadimplencia",
            action="store_true",
            help="Nao sincroniza a situacao de inadimplencia ao final.",
        )

    def handle(self, *args, **options):
        referencia = parse_month(options["mes"], timezone.localdate())
        resumo = generate_charges(referencia)
        self.stdout.write(
            self.style.SUCCESS(
                "Cobrancas de {rotulo}: {criadas} criada(s), {atualizadas} atualizada(s), "
                "{preservadas} paga(s) preservada(s).".format(
                    rotulo=month_label(referencia),
                    criadas=resumo["criadas"],
                    atualizadas=resumo["atualizadas"],
                    preservadas=resumo["preservadas"],
                )
            )
        )
        if not options["sem_inadimplencia"]:
            situacao = sync_delinquency()
            self.stdout.write(
                "Inadimplencia: {vencidas} cobranca(s) vencida(s), {marcados} cliente(s) "
                "marcado(s), {liberados} liberado(s).".format(**situacao)
            )

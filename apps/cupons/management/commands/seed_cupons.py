"""Comando ``seed_cupons``: popula cupons padrao (e, com --demo, clientes de exemplo).

Idempotente: reexecutar NAO duplica nada (usa ``get_or_create`` chaveado por
``code``/``email``). Cria os cupons padrao:

  * ANIVERSARIO10 (percentual, automatico de aniversario)
  * INDICACAO50   (valor fixo)
  * FIDELIDADE5   (percentual)
  * BOASVINDAS    (bonus / brinde)

Com ``--demo``, cria tambem alguns clientes de exemplo, incluindo 1 aniversariante
do mes atual (para demonstrar o cupom automatico).

O autor dos cupons e o primeiro superusuario existente (criado pelo entrypoint);
se nao houver usuario, ``author=None``. NAO cria ``CompanySettings`` nem
superusuario, e NAO usa campos que nao existem em ``contas.Usuario``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.cupons.models import Coupon, Customer, DiscountType

CUPONS_PADRAO = [
    {
        "code": "ANIVERSARIO10",
        "name": "Desconto de aniversario",
        "description": "10% de desconto aplicado automaticamente no mes de aniversario do cliente.",
        "discount_type": DiscountType.PERCENTUAL,
        "value": Decimal("10.00"),
        "is_birthday": True,
    },
    {
        "code": "INDICACAO50",
        "name": "Bonus por indicacao",
        "description": "R$ 50,00 de abatimento por cliente indicado.",
        "discount_type": DiscountType.FIXO,
        "value": Decimal("50.00"),
        "is_birthday": False,
    },
    {
        "code": "FIDELIDADE5",
        "name": "Fidelidade 12 meses",
        "description": "5% de desconto recorrente para clientes com mais de 12 meses de casa.",
        "discount_type": DiscountType.PERCENTUAL,
        "value": Decimal("5.00"),
        "is_birthday": False,
    },
    {
        "code": "BOASVINDAS",
        "name": "Bonus de boas-vindas",
        "description": "Brinde de boas-vindas: nao altera o valor da mensalidade.",
        "discount_type": DiscountType.BONUS,
        "value": Decimal("0.00"),
        "is_birthday": False,
    },
]

# (nome, email, telefone, mes_nasc, dia_nasc, mensalidade, nf, ativo, inadimplente)
CLIENTES_DEMO = [
    ("Ana Beatriz Souza", "ana.souza@exemplo.com.br", "(11) 98111-1001", 3, 15, "199.90", True, True, False),
    ("Bruno Carvalho Lima", "bruno.lima@exemplo.com.br", "(11) 98111-1002", 8, 2, "349.00", False, True, False),
    ("Carla Mendes Rocha", "carla.rocha@exemplo.com.br", "(21) 98111-1003", 12, 27, "129.90", True, True, True),
    ("Diego Ferreira Alves", "diego.alves@exemplo.com.br", "(31) 98111-1004", 5, 9, "89.90", False, False, False),
    ("Eduarda Pinto Ramos", "eduarda.ramos@exemplo.com.br", "(41) 98111-1005", 1, 21, "459.00", True, True, False),
    ("Felipe Andrade Nunes", "felipe.nunes@exemplo.com.br", "(51) 98111-1006", 7, 4, "249.90", False, True, False),
]


class Command(BaseCommand):
    """Cria os cupons padrao (e, com --demo, clientes de exemplo)."""

    help = "Cria os cupons padrao do modulo (idempotente). Use --demo para clientes de exemplo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Tambem cria clientes de exemplo (inclui 1 aniversariante do mes atual).",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        autor = self._obter_autor()
        self._criar_cupons(autor)
        if options["demo"]:
            self._criar_clientes_demo()
        self.stdout.write(self.style.SUCCESS("Seed de cupons concluido."))

    # -- Passos -------------------------------------------------------------
    def _obter_autor(self):
        """Primeiro superusuario existente (ou ``None``; o FK ``created_by`` e opcional)."""
        Usuario = get_user_model()
        autor = (
            Usuario.objects.filter(is_superuser=True).order_by("pk").first()
            or Usuario.objects.filter(is_staff=True).order_by("pk").first()
        )
        if autor is None:
            self.stdout.write(
                self.style.WARNING(
                    "Nenhum usuario admin encontrado; os cupons ficam sem autor (created_by=None)."
                )
            )
        return autor

    def _criar_cupons(self, autor) -> None:
        hoje = timezone.localdate()
        inicio_do_ano = date(hoje.year, 1, 1)
        criados = 0
        for dados in CUPONS_PADRAO:
            _cupom, criado = Coupon.objects.get_or_create(
                code=dados["code"],
                defaults={
                    "name": dados["name"],
                    "description": dados["description"],
                    "discount_type": dados["discount_type"],
                    "value": dados["value"],
                    "start_date": inicio_do_ano,
                    "end_date": None,
                    "is_active": True,
                    "is_birthday": dados["is_birthday"],
                    "created_by": autor,
                },
            )
            criados += int(criado)
        self.stdout.write(
            self.style.SUCCESS(
                f"Cupons padrao: {criados} criado(s), "
                f"{len(CUPONS_PADRAO) - criados} ja existia(m)."
            )
        )

    def _criar_clientes_demo(self) -> None:
        hoje = timezone.localdate()
        criados = 0
        for (nome, email, telefone, mes, dia, mensalidade,
             nota, ativo, inadimplente) in CLIENTES_DEMO:
            ano_nascimento = hoje.year - 30
            try:
                nascimento = date(ano_nascimento, mes, dia)
            except ValueError:  # 30/02 e afins
                nascimento = date(ano_nascimento, mes, 28)
            _cliente, criado = Customer.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": nome,
                    "phone": telefone,
                    "birth_date": nascimento,
                    "recurring_fee": Decimal(mensalidade),
                    "monthly_invoice": nota,
                    "is_active": ativo,
                    "is_delinquent": inadimplente,
                },
            )
            criados += int(criado)

        # Um cliente com aniversario no mes atual garante a demonstracao do
        # cupom automatico logo no primeiro acesso.
        aniversariante_email = "demo.aniversariante@exemplo.com.br"
        if not Customer.objects.filter(email=aniversariante_email).exists():
            nascimento = date(hoje.year - 28, hoje.month, min(hoje.day, 28))
            Customer.objects.create(
                full_name="Isabela Aniversariante Demo",
                email=aniversariante_email,
                phone="(11) 98111-1009",
                birth_date=nascimento,
                recurring_fee=Decimal("299.90"),
                monthly_invoice=True,
                is_active=True,
            )
            criados += 1

        self.stdout.write(self.style.SUCCESS(f"Clientes de exemplo: {criados} criado(s)."))

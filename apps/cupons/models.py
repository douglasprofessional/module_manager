"""Modelos do modulo de Cupons (unificado).

Consolida em um unico app os modelos que na origem viviam em ``coupons`` e
``customers``:

- ``Customer``: cliente da base (mensalidade, aniversario, situacao).
- ``Coupon``: cupom de desconto, bonus ou brinde.
- ``CouponAssignment``: vinculo cliente <-> cupom (recorrente ou mensal).
- ``MonthlyCharge``: fotografia mensal do valor devido (historico financeiro).

As FKs para o cliente usam ``"Customer"`` (mesmo app). ``created_by`` usa
``settings.AUTH_USER_MODEL`` (resolve para ``contas.Usuario``). As classes de
badge de situacao retornam as classes ``tag-status--*`` do design system
(equivalente ao que o modulo de SLA faz).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.cupons import pricing
from apps.cupons.dates import last_day_of_month, month_start
from apps.cupons.validators import phone_validator


# ===========================================================================
# Cliente
# ===========================================================================
class CustomerQuerySet(models.QuerySet):
    """Consultas reutilizaveis (mantem as views enxutas e evita SQL duplicado)."""

    def ativos(self):
        return self.filter(is_active=True, is_delinquent=False)

    def inativos(self):
        return self.filter(is_active=False)

    def inadimplentes(self):
        return self.filter(is_delinquent=True)

    def aniversariantes_do_mes(self, month: int):
        return self.filter(birth_date__month=month)

    def por_status(self, status: str | None):
        """Aplica o filtro de status usado no painel."""
        if status == "ativo":
            return self.ativos()
        if status == "inativo":
            return self.inativos()
        if status == "inadimplente":
            return self.inadimplentes()
        return self

    def buscar(self, termo: str | None):
        if not termo:
            return self
        return self.filter(
            models.Q(full_name__icontains=termo)
            | models.Q(email__icontains=termo)
            | models.Q(phone__icontains=termo)
        )


class Customer(models.Model):
    """
    Cliente da base. Os campos abaixo sao exatamente os informados no cadastro:
    nome, e-mail, telefone, data de nascimento, mensalidade recorrente,
    preferencia de nota fiscal, situacao ativo/inativo e inadimplencia.
    """

    full_name = models.CharField("Nome completo", max_length=150, db_index=True)
    email = models.EmailField("E-mail", max_length=254, unique=True)
    phone = models.CharField("Telefone", max_length=30, validators=[phone_validator])
    birth_date = models.DateField(
        "Data de nascimento",
        help_text="Usada para aplicar automaticamente o cupom do mes de aniversario.",
    )
    recurring_fee = models.DecimalField(
        "Mensalidade recorrente (R$)",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    monthly_invoice = models.BooleanField(
        "Emitir nota fiscal mensal",
        default=False,
        help_text="Marque quando o cliente exige nota fiscal todo mes.",
    )
    is_active = models.BooleanField("Cliente ativo", default=True)
    is_delinquent = models.BooleanField(
        "Inadimplente",
        default=False,
        help_text="Marcado automaticamente quando existe cobranca em atraso.",
    )

    created_at = models.DateTimeField("Cadastrado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    objects = CustomerQuerySet.as_manager()

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["is_active", "is_delinquent"], name="cupom_cliente_situacao_idx"),
            models.Index(fields=["birth_date"], name="cupom_cliente_nasc_idx"),
        ]

    def __str__(self) -> str:
        return self.full_name

    def get_absolute_url(self) -> str:
        return reverse("cupons:customer_detail", args=[self.pk])

    # -- Situacao -----------------------------------------------------------
    @property
    def status(self) -> str:
        if self.is_delinquent:
            return "inadimplente"
        return "ativo" if self.is_active else "inativo"

    @property
    def status_label(self) -> str:
        return {
            "ativo": "Ativo",
            "inativo": "Inativo",
            "inadimplente": "Inadimplente",
        }[self.status]

    @property
    def status_badge_class(self) -> str:
        """Classe ``tag-status--*`` do design system para a situacao do cliente."""
        return {
            "ativo": "tag-status--qualificada",
            "inativo": "tag-status--descartada",
            "inadimplente": "tag-status--erro",
        }[self.status]

    @property
    def birthday_month(self) -> int:
        return self.birth_date.month

    @property
    def birthday_display(self) -> str:
        return self.birth_date.strftime("%d/%m")


# ===========================================================================
# Cupom
# ===========================================================================
class DiscountType(models.TextChoices):
    PERCENTUAL = "PERCENTUAL", "Percentual (%)"
    FIXO = "FIXO", "Valor fixo (R$)"
    BONUS = "BONUS", "Bonus / brinde"


class ApplicationMode(models.TextChoices):
    RECORRENTE = "RECORRENTE", "Recorrente (todos os meses)"
    MENSAL = "MENSAL", "Mes especifico"


class AssignmentOrigin(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    AUTOMATICO = "AUTOMATICO", "Automatico (aniversario)"


class ChargeStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    PAGO = "PAGO", "Pago"
    ATRASADO = "ATRASADO", "Em atraso"
    CANCELADO = "CANCELADO", "Cancelado"


class CouponQuerySet(models.QuerySet):
    def disponiveis(self, hoje: date | None = None):
        """Cupons ativos, ja iniciados e ainda nao expirados."""
        hoje = hoje or timezone.localdate()
        return self.filter(
            is_active=True,
            start_date__lte=hoje,
        ).filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=hoje))

    def expirados(self, hoje: date | None = None):
        hoje = hoje or timezone.localdate()
        return self.filter(end_date__isnull=False, end_date__lt=hoje)

    def agendados(self, hoje: date | None = None):
        hoje = hoje or timezone.localdate()
        return self.filter(is_active=True, start_date__gt=hoje)

    def validos_no_mes(self, referencia: date):
        """Cupons cuja vigencia intercepta o mes de referencia."""
        inicio = month_start(referencia)
        fim = last_day_of_month(referencia)
        return self.filter(is_active=True, start_date__lte=fim).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=inicio)
        )

    def de_aniversario(self):
        return self.filter(is_birthday=True)


class Coupon(models.Model):
    """Cupom de desconto, bonus ou brinde."""

    name = models.CharField("Nome do cupom", max_length=120)
    code = models.CharField(
        "Codigo", max_length=30, unique=True,
        help_text="Identificador curto, sem espacos. Ex.: ANIVERSARIO10",
    )
    description = models.TextField("Descricao", blank=True)
    discount_type = models.CharField(
        "Tipo de desconto", max_length=12, choices=DiscountType.choices,
        default=DiscountType.PERCENTUAL,
    )
    value = models.DecimalField(
        "Valor",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Percentual (0 a 100) ou valor em reais. Para bonus, informe 0.",
    )
    start_date = models.DateField("Inicio da vigencia", default=timezone.localdate)
    end_date = models.DateField(
        "Fim da vigencia", null=True, blank=True,
        help_text="Deixe em branco para um cupom sem prazo de validade.",
    )
    is_active = models.BooleanField("Cupom ativo", default=True)
    is_birthday = models.BooleanField(
        "Aplicar automaticamente no mes de aniversario",
        default=False,
        help_text=(
            "Quando marcado, o cupom e concedido automaticamente a todos os clientes "
            "ativos que fazem aniversario no mes."
        ),
    )

    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Criado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupons_created",
    )

    objects = CouponQuerySet.as_manager()

    class Meta:
        verbose_name = "Cupom"
        verbose_name_plural = "Cupons"
        ordering = ["-is_birthday", "name"]
        indexes = [
            models.Index(fields=["is_active", "start_date"], name="cupom_vigencia_idx"),
            models.Index(fields=["end_date"], name="cupom_fim_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def get_absolute_url(self) -> str:
        return reverse("cupons:update", args=[self.pk])

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper().replace(" ", "_")
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors: dict[str, str] = {}

        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "A data final nao pode ser anterior a data inicial."

        valor = self.value if self.value is not None else Decimal("0.00")
        if self.discount_type == DiscountType.PERCENTUAL:
            if valor <= 0 or valor > 100:
                errors["value"] = "Para desconto percentual, informe um valor entre 0,01 e 100."
        elif self.discount_type == DiscountType.FIXO:
            if valor <= 0:
                errors["value"] = "Para desconto de valor fixo, informe um valor maior que zero."

        if self.is_birthday and self.discount_type == DiscountType.BONUS and valor < 0:
            errors["value"] = "Informe um valor maior ou igual a zero."

        if errors:
            raise ValidationError(errors)

    # -- Situacao -----------------------------------------------------------
    def status(self, hoje: date | None = None) -> str:
        hoje = hoje or timezone.localdate()
        if self.end_date and self.end_date < hoje:
            return "expirado"
        if not self.is_active:
            return "inativo"
        if self.start_date and self.start_date > hoje:
            return "agendado"
        return "disponivel"

    @property
    def status_label(self) -> str:
        return {
            "expirado": "Expirado",
            "inativo": "Inativo",
            "agendado": "Agendado",
            "disponivel": "Disponivel",
        }[self.status()]

    @property
    def status_badge_class(self) -> str:
        """Classe ``tag-status--*`` do design system para a situacao do cupom."""
        return {
            "expirado": "tag-status--erro",
            "inativo": "tag-status--descartada",
            "agendado": "tag-status--pendente",
            "disponivel": "tag-status--qualificada",
        }[self.status()]

    @property
    def value_display(self) -> str:
        if self.discount_type == DiscountType.PERCENTUAL:
            texto = f"{self.value:.2f}".rstrip("0").rstrip(".")
            return f"{texto}%".replace(".", ",")
        if self.discount_type == DiscountType.FIXO:
            return "R$ " + f"{self.value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return "Bonus"

    def valid_in_month(self, referencia: date) -> bool:
        """O cupom esta vigente em algum dia do mes de referencia?"""
        if not self.is_active:
            return False
        inicio = month_start(referencia)
        fim = last_day_of_month(referencia)
        if self.start_date and self.start_date > fim:
            return False
        if self.end_date and self.end_date < inicio:
            return False
        return True

    def to_pricing_input(self, origin: str = "MANUAL", mode: str = "RECORRENTE"):
        return pricing.CouponInput(
            id=self.pk,
            name=self.name,
            code=self.code,
            discount_type=self.discount_type,
            value=self.value,
            origin=origin,
            mode=mode,
        )


# ===========================================================================
# Aplicacao de cupom
# ===========================================================================
class CouponAssignmentQuerySet(models.QuerySet):
    def ativas(self):
        return self.filter(is_active=True)

    def do_mes(self, referencia: date):
        """
        Aplicacoes vigentes no mes de referencia.

        Vale tanto para RECORRENTE (start_month <= mes <= end_month/infinito)
        quanto para MENSAL (start_month == end_month == mes).
        """
        mes = month_start(referencia)
        return self.filter(is_active=True, start_month__lte=mes).filter(
            models.Q(end_month__isnull=True) | models.Q(end_month__gte=mes)
        )

    def validas_no_mes(self, referencia: date):
        """
        Aplicacoes vigentes no mes *e* com o cupom ainda valido no periodo.
        Toda a filtragem acontece no banco (uma unica consulta).
        """
        mes = month_start(referencia)
        fim = last_day_of_month(referencia)
        return (
            self.do_mes(mes)
            .filter(coupon__is_active=True, coupon__start_date__lte=fim)
            .filter(models.Q(coupon__end_date__isnull=True) | models.Q(coupon__end_date__gte=mes))
        )

    def historico_do_cliente(self, customer_id: int):
        return self.filter(customer_id=customer_id).select_related("coupon")


class CouponAssignment(models.Model):
    """
    Vinculo entre cliente e cupom.

    - RECORRENTE: vale de `start_month` em diante (ate `end_month`, se houver)
      e pode ser removida a qualquer momento pelo botao de excluir.
    - MENSAL: vale apenas para um mes (`start_month` == `end_month`).
    """

    customer = models.ForeignKey(
        "Customer",
        verbose_name="Cliente",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    coupon = models.ForeignKey(
        Coupon,
        verbose_name="Cupom",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    mode = models.CharField(
        "Forma de aplicacao", max_length=12, choices=ApplicationMode.choices,
        default=ApplicationMode.RECORRENTE,
    )
    start_month = models.DateField(
        "Mes inicial", help_text="Sempre armazenado no primeiro dia do mes."
    )
    end_month = models.DateField(
        "Mes final", null=True, blank=True,
        help_text="Em branco = recorrencia sem prazo.",
    )
    origin = models.CharField(
        "Origem", max_length=12, choices=AssignmentOrigin.choices,
        default=AssignmentOrigin.MANUAL,
    )
    is_active = models.BooleanField("Aplicacao ativa", default=True)

    created_at = models.DateTimeField("Aplicado em", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Aplicado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_created",
    )

    objects = CouponAssignmentQuerySet.as_manager()

    class Meta:
        verbose_name = "Aplicacao de cupom"
        verbose_name_plural = "Aplicacoes de cupons"
        ordering = ["-start_month", "coupon__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "coupon", "start_month"],
                condition=models.Q(is_active=True),
                name="uniq_aplicacao_ativa_por_mes",
            )
        ]
        indexes = [
            models.Index(fields=["customer", "is_active"], name="aplic_cliente_idx"),
            models.Index(fields=["start_month", "end_month"], name="aplic_periodo_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.customer} - {self.coupon}"

    def save(self, *args, **kwargs):
        # Normaliza para o primeiro dia do mes: simplifica todas as comparacoes.
        if self.start_month:
            self.start_month = month_start(self.start_month)
        if self.mode == ApplicationMode.MENSAL:
            self.end_month = self.start_month
        elif self.end_month:
            self.end_month = month_start(self.end_month)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors: dict[str, str] = {}

        if not self.start_month:
            errors["start_month"] = "Informe o mes de aplicacao."
            raise ValidationError(errors)

        inicio = month_start(self.start_month)
        fim = month_start(self.end_month) if self.end_month else None

        if self.mode == ApplicationMode.MENSAL:
            fim = inicio
        elif fim and fim < inicio:
            errors["end_month"] = "O mes final nao pode ser anterior ao mes inicial."

        # Impede que o mesmo cupom seja aplicado duas vezes ao mesmo cliente em
        # periodos que se sobrepoem (evitaria desconto em dobro).
        if self.customer_id and self.coupon_id and not errors:
            conflitos = CouponAssignment.objects.filter(
                customer_id=self.customer_id,
                coupon_id=self.coupon_id,
                is_active=True,
            ).exclude(pk=self.pk)
            for outro in conflitos:
                outro_fim = outro.end_month
                sobrepoe = (outro_fim is None or outro_fim >= inicio) and (
                    fim is None or outro.start_month <= fim
                )
                if sobrepoe:
                    errors["coupon"] = (
                        "Este cupom ja esta aplicado a este cliente em um periodo "
                        "que se sobrepoe ao informado."
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def applies_to(self, referencia: date) -> bool:
        """A aplicacao vale para o mes de referencia?"""
        if not self.is_active:
            return False
        mes = month_start(referencia)
        if self.start_month > mes:
            return False
        if self.end_month and self.end_month < mes:
            return False
        return self.coupon.valid_in_month(mes)

    @property
    def is_recurring(self) -> bool:
        return self.mode == ApplicationMode.RECORRENTE

    @property
    def is_automatic(self) -> bool:
        return self.origin == AssignmentOrigin.AUTOMATICO

    @property
    def period_display(self) -> str:
        if self.mode == ApplicationMode.MENSAL:
            return self.start_month.strftime("%m/%Y")
        if self.end_month:
            return f"{self.start_month:%m/%Y} ate {self.end_month:%m/%Y}"
        return f"a partir de {self.start_month:%m/%Y}"


# ===========================================================================
# Cobranca mensal
# ===========================================================================
class MonthlyChargeQuerySet(models.QuerySet):
    def do_mes(self, referencia: date):
        return self.filter(reference_month=month_start(referencia))

    def em_aberto(self):
        return self.filter(status__in=[ChargeStatus.PENDENTE, ChargeStatus.ATRASADO])


class MonthlyCharge(models.Model):
    """
    Fotografia mensal do valor devido pelo cliente (base - descontos).

    Serve de historico financeiro: mesmo que um cupom seja alterado depois, a
    cobranca ja gerada preserva os valores praticados no mes.
    """

    customer = models.ForeignKey(
        "Customer",
        verbose_name="Cliente",
        on_delete=models.CASCADE,
        related_name="charges",
    )
    reference_month = models.DateField("Mes de referencia")
    base_amount = models.DecimalField(
        "Mensalidade (R$)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        "Desconto (R$)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    final_amount = models.DecimalField(
        "Valor final (R$)", max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    coupons_summary = models.CharField("Cupons aplicados", max_length=255, blank=True)
    bonus_summary = models.CharField("Bonus concedidos", max_length=255, blank=True)
    invoice_required = models.BooleanField("Nota fiscal solicitada", default=False)
    status = models.CharField(
        "Situacao", max_length=10, choices=ChargeStatus.choices, default=ChargeStatus.PENDENTE
    )
    due_date = models.DateField("Vencimento", null=True, blank=True)
    paid_at = models.DateTimeField("Pago em", null=True, blank=True)

    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    objects = MonthlyChargeQuerySet.as_manager()

    class Meta:
        verbose_name = "Cobranca mensal"
        verbose_name_plural = "Cobrancas mensais"
        ordering = ["-reference_month", "customer__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "reference_month"], name="uniq_cobranca_cliente_mes"
            )
        ]
        indexes = [
            models.Index(fields=["reference_month", "status"], name="cobranca_mes_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.customer} - {self.reference_month:%m/%Y}"

    def save(self, *args, **kwargs):
        if self.reference_month:
            self.reference_month = month_start(self.reference_month)
        super().save(*args, **kwargs)

    @property
    def status_badge_class(self) -> str:
        """Classe ``tag-status--*`` do design system para a situacao da cobranca."""
        return {
            ChargeStatus.PENDENTE: "tag-status--pendente",
            ChargeStatus.PAGO: "tag-status--concluida",
            ChargeStatus.ATRASADO: "tag-status--erro",
            ChargeStatus.CANCELADO: "tag-status--descartada",
        }.get(self.status, "tag-status--descartada")

    @property
    def is_open(self) -> bool:
        return self.status in {ChargeStatus.PENDENTE, ChargeStatus.ATRASADO}

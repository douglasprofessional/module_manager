"""Formularios do modulo de Cupons (cupons, aplicacoes, cobrancas e clientes).

O antigo ``BootstrapFormMixin`` (de ``apps.core.forms``) foi substituido por um
mixin local, ``CamposDesignMixin``, que aplica as classes do design system da
plataforma (``campo`` para entradas/selecoes/textareas, ``campo-arquivo`` para
uploads). Checkboxes ficam sem classe (o template os renderiza como
``campo-check``). Nao ha dependencia de Bootstrap.
"""

from __future__ import annotations

import re
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.cupons.dates import month_start
from apps.cupons.models import (
    ApplicationMode,
    ChargeStatus,
    Coupon,
    CouponAssignment,
    Customer,
    DiscountType,
    MonthlyCharge,
)

CODIGO_RE = re.compile(r"^[A-Z0-9_\-]{2,30}$")
IDADE_MAXIMA_ANOS = 120


class CamposDesignMixin:
    """Aplica as classes do design system aos widgets do formulario.

    - ``CheckboxInput``: sem classe (renderizado como ``campo-check`` no template).
    - ``FileInput``/``ClearableFileInput``: classe ``campo-arquivo``.
    - Demais (texto, e-mail, numero, data, select, textarea): classe ``campo``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            if isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
                widget.attrs.setdefault("class", "campo-arquivo")
                continue
            classe = widget.attrs.get("class", "")
            if "campo" not in classe.split():
                widget.attrs["class"] = (classe + " campo").strip()


def cupons_nao_expirados(hoje):
    """Q() de cupons ainda nao expirados (usado no seletor de aplicacao)."""
    return Q(end_date__isnull=True) | Q(end_date__gte=hoje)


class MonthField(forms.DateField):
    """Campo <input type="month"> convertido para o primeiro dia do mes."""

    widget = forms.DateInput(attrs={"type": "month"}, format="%Y-%m")

    def __init__(self, **kwargs):
        kwargs.setdefault("input_formats", ["%Y-%m", "%Y-%m-%d"])
        super().__init__(**kwargs)

    def to_python(self, value):
        valor = super().to_python(value)
        return month_start(valor) if valor else valor


class CouponForm(CamposDesignMixin, forms.ModelForm):
    """Cadastro/edicao de cupom com vigencia (datepicker) e tipo de desconto."""

    start_date = forms.DateField(
        label="Inicio da vigencia",
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        initial=timezone.localdate,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        label="Fim da vigencia",
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        help_text="Deixe em branco para um cupom sem prazo de validade.",
    )

    class Meta:
        model = Coupon
        fields = [
            "name",
            "code",
            "description",
            "discount_type",
            "value",
            "start_date",
            "end_date",
            "is_active",
            "is_birthday",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Desconto de aniversario"}),
            "code": forms.TextInput(attrs={"placeholder": "ANIVERSARIO10"}),
            "description": forms.Textarea(attrs={"placeholder": "Detalhes internos do cupom", "rows": 3}),
            "value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def clean_code(self):
        codigo = (self.cleaned_data.get("code") or "").strip().upper().replace(" ", "_")
        if not CODIGO_RE.match(codigo):
            raise ValidationError(
                "Use de 2 a 30 caracteres: letras, numeros, hifen ou sublinhado."
            )
        return codigo

    def clean(self):
        limpos = super().clean()
        tipo = limpos.get("discount_type")
        valor = limpos.get("value")

        # Bonus nao altera o valor da mensalidade: normalizamos para zero.
        if tipo == DiscountType.BONUS:
            limpos["value"] = 0
            self.instance.value = 0
        elif valor is None:
            self.add_error("value", "Informe o valor do desconto.")
        return limpos


class CouponAssignmentForm(CamposDesignMixin, forms.ModelForm):
    """
    Aplicacao de um cupom a um cliente.

    - Recorrente: vale de um mes em diante (opcionalmente ate um mes final).
    - Mes especifico: vale apenas para o mes escolhido.
    """

    start_month = MonthField(label="Mes inicial")
    end_month = MonthField(
        label="Mes final (opcional)",
        required=False,
        help_text="Somente para aplicacao recorrente. Em branco = sem prazo.",
    )

    class Meta:
        model = CouponAssignment
        fields = ["coupon", "mode", "start_month", "end_month"]
        labels = {"coupon": "Cupom", "mode": "Forma de aplicacao"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = timezone.localdate()
        self.fields["coupon"].queryset = (
            Coupon.objects.filter(is_active=True)
            .filter(cupons_nao_expirados(hoje))
            .order_by("-is_birthday", "name")
        )
        self.fields["coupon"].empty_label = "Selecione um cupom"
        if not self.initial.get("start_month") and not self.instance.pk:
            self.initial["start_month"] = month_start(hoje)

    def clean(self):
        limpos = super().clean()
        if limpos.get("mode") == ApplicationMode.MENSAL:
            # No modo mensal o periodo e sempre de um unico mes.
            limpos["end_month"] = limpos.get("start_month")
            self.instance.end_month = limpos.get("start_month")
        return limpos


class ChargeStatusForm(CamposDesignMixin, forms.ModelForm):
    """Atualizacao manual da situacao de uma cobranca."""

    class Meta:
        model = MonthlyCharge
        fields = ["status", "due_date"]
        widgets = {
            "due_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["due_date"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["due_date"].required = False

    def clean(self):
        limpos = super().clean()
        if limpos.get("status") == ChargeStatus.PAGO and not self.instance.paid_at:
            self.instance.paid_at = timezone.now()
        elif limpos.get("status") != ChargeStatus.PAGO:
            self.instance.paid_at = None
        return limpos


class CustomerForm(CamposDesignMixin, forms.ModelForm):
    """
    Painel de cadastro do cliente. Todos os dados sao informados aqui - nao ha
    campos gerados automaticamente alem dos carimbos de data de criacao/edicao.
    """

    birth_date = forms.DateField(
        label="Data de nascimento",
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date", "max": date.today().isoformat()},
        ),
        help_text="Usada para conceder automaticamente o cupom do mes de aniversario.",
    )

    class Meta:
        model = Customer
        fields = [
            "full_name",
            "email",
            "phone",
            "birth_date",
            "recurring_fee",
            "monthly_invoice",
            "is_active",
            "is_delinquent",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Nome completo do cliente"}),
            "email": forms.EmailInput(attrs={"placeholder": "cliente@email.com.br"}),
            "phone": forms.TextInput(attrs={"placeholder": "(11) 98888-7777"}),
            "recurring_fee": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "placeholder": "0,00"}
            ),
        }
        labels = {
            "recurring_fee": "Mensalidade recorrente (R$)",
            "monthly_invoice": "Emitir nota fiscal mensal",
            "is_active": "Cliente ativo",
            "is_delinquent": "Inadimplente",
        }
        help_texts = {
            "recurring_fee": "Valor cheio da assinatura, antes dos cupons.",
            "is_delinquent": "Atualizado automaticamente quando ha cobranca vencida.",
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        return email

    def clean_full_name(self):
        nome = " ".join((self.cleaned_data.get("full_name") or "").split())
        if len(nome) < 3:
            raise ValidationError("Informe o nome completo do cliente.")
        return nome

    def clean_birth_date(self):
        nascimento = self.cleaned_data.get("birth_date")
        if not nascimento:
            return nascimento
        hoje = date.today()
        if nascimento > hoje:
            raise ValidationError("A data de nascimento nao pode estar no futuro.")
        if nascimento.year < hoje.year - IDADE_MAXIMA_ANOS:
            raise ValidationError("Confira a data de nascimento informada.")
        return nascimento

    def clean_recurring_fee(self):
        valor = self.cleaned_data.get("recurring_fee")
        if valor is not None and valor < 0:
            raise ValidationError("A mensalidade nao pode ser negativa.")
        return valor

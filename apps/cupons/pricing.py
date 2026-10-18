"""
Motor de calculo da mensalidade com cupons.

Este modulo e *puro*: nao importa Django nem toca no banco. Isso permite testar
a regra de negocio isoladamente e reutiliza-la em relatorios, APIs ou tarefas
agendadas.

Regras de aplicacao (nesta ordem):

1. A base do calculo e a mensalidade recorrente do cliente.
2. Cupons PERCENTUAL sao somados; a soma e limitada a 100%.
3. Cupons FIXO sao somados em reais.
4. O desconto total nunca ultrapassa a mensalidade (o valor final e >= 0).
   Se ultrapassar, o abatimento e rateado proporcionalmente entre os cupons,
   de forma que a soma das atribuicoes seja exatamente igual ao desconto total.
5. Cupons BONUS nao alteram o valor a pagar: representam brindes/creditos e sao
   listados separadamente na fatura.
6. Todos os valores monetarios sao arredondados para 2 casas (ROUND_HALF_UP).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("0.01")
MAX_PERCENT = Decimal("100")

# Tipos de desconto (espelham apps.cupons.models.DiscountType)
PERCENTUAL = "PERCENTUAL"
FIXO = "FIXO"
BONUS = "BONUS"


def money(value) -> Decimal:
    """Converte para Decimal com 2 casas decimais (arredondamento comercial)."""
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            value = Decimal("0")
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CouponInput:
    """Representacao minima de um cupom para o calculo."""

    id: int
    name: str
    discount_type: str
    value: Decimal
    code: str = ""
    origin: str = "MANUAL"
    mode: str = "RECORRENTE"

    @property
    def is_bonus(self) -> bool:
        return self.discount_type == BONUS


@dataclass(frozen=True)
class AppliedCoupon:
    """Cupom aplicado e quanto ele efetivamente abateu da mensalidade."""

    coupon: CouponInput
    discount: Decimal

    @property
    def name(self) -> str:
        return self.coupon.name


@dataclass
class PricingResult:
    """Resultado do calculo mensal de um cliente."""

    base_amount: Decimal
    percent_rate: Decimal = Decimal("0")
    percent_discount: Decimal = Decimal("0.00")
    fixed_discount: Decimal = Decimal("0.00")
    total_discount: Decimal = Decimal("0.00")
    final_amount: Decimal = Decimal("0.00")
    capped: bool = False
    applied: list[AppliedCoupon] = field(default_factory=list)
    bonuses: list[CouponInput] = field(default_factory=list)

    @property
    def has_discount(self) -> bool:
        return self.total_discount > 0

    @property
    def discount_percent_of_base(self) -> Decimal:
        """Percentual efetivo de desconto sobre a mensalidade."""
        if self.base_amount <= 0:
            return Decimal("0.00")
        return (self.total_discount / self.base_amount * 100).quantize(
            CENTS, rounding=ROUND_HALF_UP
        )

    @property
    def bonus_names(self) -> list[str]:
        return [bonus.name for bonus in self.bonuses]


def _distribute(values: list[Decimal], target: Decimal) -> list[Decimal]:
    """
    Ajusta `values` para que a soma seja exatamente `target`, preservando a
    proporcao entre os itens. Sobras de arredondamento vao para o maior item.
    """
    quantized = [money(v) for v in values]
    current = sum(quantized, Decimal("0.00"))
    if not quantized or current == target:
        return quantized
    if current <= 0:
        return quantized

    factor = target / current
    scaled = [money(v * factor) for v in quantized]
    residue = money(target - sum(scaled, Decimal("0.00")))
    if residue != 0:
        idx = scaled.index(max(scaled))
        scaled[idx] = money(scaled[idx] + residue)
    return scaled


def calculate_monthly_amount(base_amount, coupons) -> PricingResult:
    """
    Calcula o valor mensal do cliente aplicando a lista de cupons informada.

    :param base_amount: mensalidade recorrente (Decimal/str/float)
    :param coupons: iteravel de CouponInput
    :return: PricingResult com o detalhamento completo
    """
    base = money(base_amount)
    if base < 0:
        base = Decimal("0.00")

    coupons = list(coupons or [])
    bonuses = [c for c in coupons if c.discount_type == BONUS]
    descontos = [c for c in coupons if c.discount_type in (PERCENTUAL, FIXO)]

    if not descontos:
        # Somente bonus (ou nenhum cupom): o valor a pagar nao muda.
        return PricingResult(
            base_amount=base,
            final_amount=base,
            applied=[AppliedCoupon(coupon=b, discount=Decimal("0.00")) for b in bonuses],
            bonuses=bonuses,
        )

    # 1) Soma dos percentuais, limitada a 100%.
    rate_sum = sum(
        (money(c.value) for c in descontos if c.discount_type == PERCENTUAL),
        Decimal("0.00"),
    )
    effective_rate = min(rate_sum, MAX_PERCENT)
    rate_factor = (effective_rate / rate_sum) if rate_sum > 0 else Decimal("0")

    # 2) Valor bruto de cada cupom.
    raw: list[Decimal] = []
    for coupon in descontos:
        if coupon.discount_type == PERCENTUAL:
            raw.append(base * money(coupon.value) * rate_factor / Decimal("100"))
        else:  # FIXO
            raw.append(money(coupon.value))

    raw_total = sum((money(v) for v in raw), Decimal("0.00"))

    # 3) O desconto total nunca ultrapassa a mensalidade.
    total_discount = min(raw_total, base)
    capped = raw_total > base

    # 4) Rateio para que a soma das atribuicoes bata com o total.
    distributed = _distribute(raw, total_discount)

    applied: list[AppliedCoupon] = []
    percent_discount = Decimal("0.00")
    fixed_discount = Decimal("0.00")
    for coupon, discount in zip(descontos, distributed):
        applied.append(AppliedCoupon(coupon=coupon, discount=discount))
        if coupon.discount_type == PERCENTUAL:
            percent_discount += discount
        else:
            fixed_discount += discount

    # Bonus entram na lista de aplicados com abatimento zero (aparecem na fatura).
    for bonus in bonuses:
        applied.append(AppliedCoupon(coupon=bonus, discount=Decimal("0.00")))

    return PricingResult(
        base_amount=base,
        percent_rate=effective_rate,
        percent_discount=money(percent_discount),
        fixed_discount=money(fixed_discount),
        total_discount=money(total_discount),
        final_amount=money(base - total_discount),
        capped=capped,
        applied=applied,
        bonuses=bonuses,
    )

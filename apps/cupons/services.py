"""
Servicos de dominio: aplicacao automatica de cupons, calculo mensal,
geracao de cobrancas, inadimplencia e metricas do painel.

Toda a logica que envolve mais de um modelo vive aqui - as views ficam finas e
as regras podem ser reaproveitadas por comandos de gerenciamento e testes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.utils import timezone

from apps.cupons.dates import due_date_for, month_start
from apps.cupons.models import (
    ApplicationMode,
    AssignmentOrigin,
    ChargeStatus,
    Coupon,
    CouponAssignment,
    Customer,
    MonthlyCharge,
)
from apps.cupons.pricing import CouponInput, PricingResult, calculate_monthly_amount

logger = logging.getLogger(__name__)

DASHBOARD_VERSION_KEY = "dashboard:version"
ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Cache do painel (invalidacao por versao: O(1), sem varrer chaves)
# ---------------------------------------------------------------------------
def dashboard_version() -> int:
    version = cache.get(DASHBOARD_VERSION_KEY)
    if version is None:
        cache.set(DASHBOARD_VERSION_KEY, 1, None)
        return 1
    return int(version)


def bump_dashboard_version() -> None:
    """Invalida todas as metricas cacheadas (chamado pelos signals)."""
    try:
        cache.incr(DASHBOARD_VERSION_KEY)
    except ValueError:
        cache.set(DASHBOARD_VERSION_KEY, 1, None)


# ---------------------------------------------------------------------------
# Conversao modelo -> entrada do motor de calculo
# ---------------------------------------------------------------------------
def assignment_to_input(assignment: CouponAssignment) -> CouponInput:
    coupon = assignment.coupon
    return CouponInput(
        id=coupon.pk,
        name=coupon.name,
        code=coupon.code,
        discount_type=coupon.discount_type,
        value=coupon.value,
        origin=assignment.origin,
        mode=assignment.mode,
    )


def prefetch_month_assignments(queryset, referencia: date):
    """
    Anexa a cada cliente a lista `cupons_do_mes` (aplicacoes validas no mes),
    em uma unica consulta extra - evita N+1 na tabela do painel.
    """
    mes = month_start(referencia)
    aplicacoes = CouponAssignment.objects.validas_no_mes(mes).select_related("coupon")
    return queryset.prefetch_related(
        Prefetch("assignments", queryset=aplicacoes, to_attr="cupons_do_mes")
    )


def pricing_from_prefetched(customer: Customer) -> PricingResult:
    """Calculo usando a lista ja carregada por `prefetch_month_assignments`."""
    aplicacoes = getattr(customer, "cupons_do_mes", [])
    return calculate_monthly_amount(
        customer.recurring_fee, [assignment_to_input(a) for a in aplicacoes]
    )


def customer_pricing(customer: Customer, referencia: date) -> PricingResult:
    """Calculo da mensalidade de um cliente em um mes (consulta o banco)."""
    mes = month_start(referencia)
    aplicacoes = (
        CouponAssignment.objects.validas_no_mes(mes)
        .filter(customer=customer)
        .select_related("coupon")
    )
    return calculate_monthly_amount(
        customer.recurring_fee, [assignment_to_input(a) for a in aplicacoes]
    )


# ---------------------------------------------------------------------------
# Cupom automatico de aniversario
# ---------------------------------------------------------------------------
def birthday_cache_key(referencia: date) -> str:
    return f"aniversario:aplicado:{month_start(referencia):%Y-%m}"


def invalidate_birthday_cache(referencia: date) -> None:
    cache.delete(birthday_cache_key(referencia))


@transaction.atomic
def ensure_birthday_assignments(referencia: date, *, force: bool = False) -> int:
    """
    Garante que todo cliente ATIVO que faz aniversario no mes de referencia
    possua a aplicacao automatica dos cupons marcados como "de aniversario".

    A operacao e idempotente: rodar varias vezes nao duplica aplicacoes.
    Retorna a quantidade de aplicacoes criadas.
    """
    mes = month_start(referencia)

    # Sem `force`, so executa uma vez por hora por mes de referencia.
    if not force and not cache.add(birthday_cache_key(mes), 1, 3600):
        return 0

    cupons = list(Coupon.objects.de_aniversario().validos_no_mes(mes))
    if not cupons:
        logger.debug("Nenhum cupom de aniversario vigente em %s.", mes)
        return 0

    aniversariantes = list(
        Customer.objects.filter(is_active=True, birth_date__month=mes.month).only("id")
    )
    if not aniversariantes:
        return 0

    ids_clientes = [c.pk for c in aniversariantes]
    ids_cupons = [c.pk for c in cupons]

    existentes = set(
        CouponAssignment.objects.do_mes(mes)
        .filter(customer_id__in=ids_clientes, coupon_id__in=ids_cupons)
        .values_list("customer_id", "coupon_id")
    )

    novas = [
        CouponAssignment(
            customer_id=cliente.pk,
            coupon_id=cupom.pk,
            mode=ApplicationMode.MENSAL,
            start_month=mes,
            end_month=mes,
            origin=AssignmentOrigin.AUTOMATICO,
            is_active=True,
        )
        for cliente in aniversariantes
        for cupom in cupons
        if (cliente.pk, cupom.pk) not in existentes
    ]

    if not novas:
        return 0

    # ignore_conflicts protege contra concorrencia (2 workers ao mesmo tempo).
    CouponAssignment.objects.bulk_create(novas, ignore_conflicts=True)
    bump_dashboard_version()
    logger.info(
        "Cupom de aniversario aplicado a %s cliente(s) em %s.", len(novas), mes.strftime("%m/%Y")
    )
    return len(novas)


# ---------------------------------------------------------------------------
# Cobrancas mensais
# ---------------------------------------------------------------------------
def _resumo(nomes: list[str], limite: int = 255) -> str:
    texto = ", ".join(nomes)
    return texto if len(texto) <= limite else texto[: limite - 3] + "..."


@transaction.atomic
def generate_charges(referencia: date, *, aplicar_aniversario: bool = True) -> dict:
    """
    Gera (ou atualiza) as cobrancas do mes para todos os clientes ativos.

    Cobrancas ja quitadas (PAGO) nunca sao sobrescritas - preservam o historico.
    """
    mes = month_start(referencia)
    if aplicar_aniversario:
        ensure_birthday_assignments(mes, force=True)

    pagas = set(
        MonthlyCharge.objects.filter(reference_month=mes, status=ChargeStatus.PAGO).values_list(
            "customer_id", flat=True
        )
    )

    criadas = atualizadas = preservadas = 0
    vencimento = due_date_for(mes)

    clientes = prefetch_month_assignments(Customer.objects.filter(is_active=True), mes)
    for customer in clientes.iterator(chunk_size=200):
        if customer.pk in pagas:
            preservadas += 1
            continue

        resultado = pricing_from_prefetched(customer)
        _charge, created = MonthlyCharge.objects.update_or_create(
            customer=customer,
            reference_month=mes,
            defaults={
                "base_amount": resultado.base_amount,
                "discount_amount": resultado.total_discount,
                "final_amount": resultado.final_amount,
                "coupons_summary": _resumo(
                    [a.coupon.name for a in resultado.applied if a.discount > 0]
                ),
                "bonus_summary": _resumo(resultado.bonus_names),
                "invoice_required": customer.monthly_invoice,
                "due_date": vencimento,
            },
        )
        criadas += int(created)
        atualizadas += int(not created)

    bump_dashboard_version()
    resumo = {
        "mes": mes,
        "criadas": criadas,
        "atualizadas": atualizadas,
        "preservadas": preservadas,
    }
    logger.info("Cobrancas geradas para %s: %s", mes.strftime("%m/%Y"), resumo)
    return resumo


def sync_delinquency(customer: Customer | None = None) -> dict:
    """
    Marca cobrancas vencidas como ATRASADO e sincroniza o campo
    `is_delinquent` dos clientes. Retorna um resumo da operacao.
    """
    hoje = timezone.localdate()

    vencidas_qs = MonthlyCharge.objects.filter(
        status=ChargeStatus.PENDENTE, due_date__isnull=False, due_date__lt=hoje
    )
    if customer is not None:
        vencidas_qs = vencidas_qs.filter(customer=customer)
    vencidas = vencidas_qs.update(status=ChargeStatus.ATRASADO)

    clientes = Customer.objects.all()
    if customer is not None:
        clientes = clientes.filter(pk=customer.pk)

    em_atraso = MonthlyCharge.objects.filter(status=ChargeStatus.ATRASADO).values("customer_id")
    marcados = clientes.filter(is_delinquent=False, id__in=em_atraso).update(is_delinquent=True)
    liberados = clientes.filter(is_delinquent=True).exclude(id__in=em_atraso).update(
        is_delinquent=False
    )

    if vencidas or marcados or liberados:
        bump_dashboard_version()
        logger.info(
            "Inadimplencia sincronizada: %s vencidas, %s marcados, %s liberados.",
            vencidas, marcados, liberados,
        )
    return {"vencidas": vencidas, "marcados": marcados, "liberados": liberados}


# ---------------------------------------------------------------------------
# Metricas do painel
# ---------------------------------------------------------------------------
def _financeiro_do_mes(mes: date) -> dict:
    """
    Soma mensalidades, descontos e valor liquido do mes usando apenas duas
    consultas (aplicacoes + clientes ativos).
    """
    por_cliente: dict[int, list[CouponInput]] = defaultdict(list)
    campos = (
        "customer_id", "coupon_id", "coupon__name", "coupon__code",
        "coupon__discount_type", "coupon__value", "origin", "mode",
    )
    for linha in CouponAssignment.objects.validas_no_mes(mes).values_list(*campos):
        cliente_id, cupom_id, nome, codigo, tipo, valor, origem, modo = linha
        por_cliente[cliente_id].append(
            CouponInput(
                id=cupom_id, name=nome, code=codigo, discount_type=tipo,
                value=valor, origin=origem, mode=modo,
            )
        )

    bruto = desconto = liquido = ZERO
    for cliente_id, mensalidade in Customer.objects.filter(is_active=True).values_list(
        "id", "recurring_fee"
    ):
        resultado = calculate_monthly_amount(mensalidade, por_cliente.get(cliente_id, []))
        bruto += resultado.base_amount
        desconto += resultado.total_discount
        liquido += resultado.final_amount

    return {"faturamento_bruto": bruto, "descontos": desconto, "faturamento_liquido": liquido}


def dashboard_metrics(referencia: date) -> dict:
    """Metricas do painel (cacheadas por CACHE_TTL_DASHBOARD segundos)."""
    mes = month_start(referencia)
    chave = f"dashboard:metrics:v{dashboard_version()}:{mes:%Y-%m}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado

    hoje = timezone.localdate()
    aplicacoes_mes = CouponAssignment.objects.validas_no_mes(mes)

    clientes = Customer.objects.aggregate(
        total=Count("id"),
        ativos=Count("id", filter=Q(is_active=True, is_delinquent=False)),
        inativos=Count("id", filter=Q(is_active=False)),
        inadimplentes=Count("id", filter=Q(is_delinquent=True)),
        aniversariantes=Count("id", filter=Q(is_active=True, birth_date__month=mes.month)),
    )

    metricas = {
        "mes": mes,
        "cupons_criados": Coupon.objects.count(),
        "cupons_disponiveis": Coupon.objects.disponiveis(hoje).count(),
        "cupons_expirados": Coupon.objects.expirados(hoje).count(),
        "cupons_ativos": aplicacoes_mes.values("coupon_id").distinct().count(),
        "aplicacoes_no_mes": aplicacoes_mes.count(),
        "clientes": clientes,
        "cobrancas_em_aberto": MonthlyCharge.objects.do_mes(mes).em_aberto().count(),
    }
    metricas.update(_financeiro_do_mes(mes))

    cache.set(chave, metricas, getattr(settings, "CACHE_TTL_DASHBOARD", 120))
    return metricas


# ---------------------------------------------------------------------------
# Filtros do painel
# ---------------------------------------------------------------------------
def filter_customers(queryset, *, referencia: date, coupon_id=None, aplicacao: str | None = None):
    """
    Aplica os filtros de cupom do painel:

    - `atual`     : clientes com o cupom aplicado no mes de referencia
    - `historico` : clientes que ja receberam o cupom em qualquer periodo
    - `sem`       : clientes sem nenhum cupom no mes de referencia
    """
    mes = month_start(referencia)

    if aplicacao == "sem":
        sem_cupom = CouponAssignment.objects.validas_no_mes(mes).filter(customer=OuterRef("pk"))
        if coupon_id:
            sem_cupom = sem_cupom.filter(coupon_id=coupon_id)
        return queryset.filter(~Exists(sem_cupom))

    if aplicacao == "historico":
        historico = CouponAssignment.objects.filter(customer=OuterRef("pk"))
        if coupon_id:
            historico = historico.filter(coupon_id=coupon_id)
        return queryset.filter(Exists(historico))

    if aplicacao == "atual" or coupon_id:
        atual = CouponAssignment.objects.validas_no_mes(mes).filter(customer=OuterRef("pk"))
        if coupon_id:
            atual = atual.filter(coupon_id=coupon_id)
        return queryset.filter(Exists(atual))

    return queryset

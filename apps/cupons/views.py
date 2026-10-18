"""Views do modulo de Cupons.

Consolida as antigas views de ``coupons``, ``customers`` e o painel de
``core.dashboard`` em um unico modulo. Mudancas em relacao a origem:

- Acesso: ``@login_required`` + ``@role_required(...)`` -> ``@admin_requerido``
  (o ``SomenteAdminMiddleware`` ja protege o site; isto e defesa em profundidade).
- Todos os ``reverse``/``redirect`` usam o namespace ``cupons:``.
- Acoes de escrita registram auditoria via ``apps.nucleo.models.RegistroAuditoria``.
- As telas de white-label/settings, ``set_theme`` e ``health`` foram removidas
  (pertencem ao nucleo).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.contas.decorators import admin_requerido
from apps.nucleo.textos import texto
from apps.cupons.dates import month_label, month_options, parse_month
from apps.cupons.forms import (
    ChargeStatusForm,
    CouponAssignmentForm,
    CouponForm,
    CustomerForm,
)
from apps.cupons.models import (
    ChargeStatus,
    Coupon,
    CouponAssignment,
    Customer,
    MonthlyCharge,
)
from apps.cupons.services import (
    customer_pricing,
    dashboard_metrics,
    ensure_birthday_assignments,
    filter_customers,
    generate_charges,
    invalidate_birthday_cache,
    prefetch_month_assignments,
    pricing_from_prefetched,
    sync_delinquency,
)

logger = logging.getLogger("modulos.cupons.views")

FILTROS_CUPOM = {"disponivel", "expirado", "agendado", "inativo", "aniversario"}
STATUS_VALIDOS = {"ativo", "inativo", "inadimplente"}
APLICACAO_VALIDA = {"atual", "historico", "sem"}

# Paginacao (configuravel por settings; getattr com padrao para nao exigir
# nenhuma chave de negocio no settings compartilhado).
COUPONS_PER_PAGE = getattr(settings, "COUPONS_PER_PAGE", 12)
CUSTOMERS_PER_PAGE = getattr(settings, "CUSTOMERS_PER_PAGE", 20)
CHARGES_PER_PAGE = getattr(settings, "CHARGES_PER_PAGE", 20)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _ip(request: HttpRequest) -> str | None:
    """IP do cliente (REMOTE_ADDR); nao confia em cabecalhos de proxy."""
    return request.META.get("REMOTE_ADDR") or None


def _auditar(request: HttpRequest, acao: str, objeto: str = "") -> None:
    """Registra um evento de auditoria sem nunca quebrar o fluxo da view."""
    try:
        from apps.nucleo.models import RegistroAuditoria

        usuario = request.user if getattr(request.user, "is_authenticated", False) else None
        RegistroAuditoria.objects.create(
            usuario=usuario,
            acao=acao,
            objeto_repr=(objeto or "")[:255],
            ip=_ip(request),
        )
    except Exception:  # auditoria e best-effort
        logger.exception("Falha ao registrar auditoria (acao=%s).", acao)


def _destino_seguro(request: HttpRequest) -> str:
    """Retorna o ``next`` do POST apenas se for da própria origem (anti open redirect)."""
    destino = request.POST.get("next") or ""
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return ""


def _erros_como_texto(form) -> str:
    partes = []
    for campo, erros in form.errors.items():
        rotulo = form.fields[campo].label if campo in form.fields else "Formulario"
        partes.append(f"{rotulo}: {' '.join(erros)}")
    return " | ".join(partes) or "Dados invalidos."


# ---------------------------------------------------------------------------
# Painel (antiga core.dashboard)
# ---------------------------------------------------------------------------
@admin_requerido
def painel(request: HttpRequest) -> HttpResponse:
    """
    Pagina inicial do modulo: metricas de cupons + tabela paginada de clientes
    com filtros de situacao e de aplicacao de cupons.
    """
    hoje = timezone.localdate()
    referencia = parse_month(request.GET.get("mes"), hoje)

    # Concede o cupom de aniversario do mes (idempotente e protegido por cache).
    try:
        ensure_birthday_assignments(referencia)
    except Exception:  # pragma: no cover - nunca derruba o painel
        logger.exception("Falha ao aplicar cupons de aniversario de %s.", referencia)

    status = request.GET.get("status", "")
    status = status if status in STATUS_VALIDOS else ""
    termo = (request.GET.get("q") or "").strip()
    aplicacao = request.GET.get("aplicacao", "")
    aplicacao = aplicacao if aplicacao in APLICACAO_VALIDA else ""
    cupom_param = (request.GET.get("cupom") or "").strip()
    cupom_id = int(cupom_param) if cupom_param.isdigit() else None

    clientes = Customer.objects.all().por_status(status).buscar(termo)
    clientes = filter_customers(
        clientes, referencia=referencia, coupon_id=cupom_id, aplicacao=aplicacao
    )
    clientes = prefetch_month_assignments(clientes, referencia).annotate(
        total_aplicacoes=Count("assignments", distinct=True)
    )

    paginador = Paginator(clientes, CUSTOMERS_PER_PAGE)
    pagina = paginador.get_page(request.GET.get("page"))

    # O calculo roda sobre os cupons ja pre-carregados: nenhuma consulta extra.
    linhas = [
        {
            "cliente": cliente,
            "calculo": pricing_from_prefetched(cliente),
            "cupons": getattr(cliente, "cupons_do_mes", []),
        }
        for cliente in pagina.object_list
    ]

    contexto = {
        "metricas": dashboard_metrics(referencia),
        "pagina": pagina,
        "linhas": linhas,
        "referencia": referencia,
        "referencia_label": month_label(referencia),
        "meses": month_options(hoje, back=12, forward=3),
        "cupons": Coupon.objects.all().only("id", "name", "code"),
        "filtros": {
            "status": status,
            "q": termo,
            "aplicacao": aplicacao,
            "cupom": cupom_param if cupom_id else "",
            "mes": referencia.strftime("%Y-%m"),
        },
        "total_resultados": paginador.count,
    }
    return render(request, "cupons/painel.html", contexto)


# ---------------------------------------------------------------------------
# Cupons
# ---------------------------------------------------------------------------
@admin_requerido
def coupon_list(request: HttpRequest) -> HttpResponse:
    """Lista de cupons com filtro por situacao e busca por nome/codigo."""
    hoje = timezone.localdate()
    situacao = request.GET.get("situacao", "")
    situacao = situacao if situacao in FILTROS_CUPOM else ""
    termo = (request.GET.get("q") or "").strip()

    cupons = Coupon.objects.all()
    if situacao == "disponivel":
        cupons = cupons.disponiveis(hoje)
    elif situacao == "expirado":
        cupons = cupons.expirados(hoje)
    elif situacao == "agendado":
        cupons = cupons.agendados(hoje)
    elif situacao == "inativo":
        cupons = cupons.filter(is_active=False)
    elif situacao == "aniversario":
        cupons = cupons.de_aniversario()

    if termo:
        cupons = cupons.filter(Q(name__icontains=termo) | Q(code__icontains=termo))

    cupons = cupons.annotate(
        aplicacoes_ativas=Count(
            "assignments", filter=Q(assignments__is_active=True), distinct=True
        )
    ).order_by("-is_birthday", "name")

    paginador = Paginator(cupons, COUPONS_PER_PAGE)
    pagina = paginador.get_page(request.GET.get("page"))

    contexto = {
        "pagina": pagina,
        "total_resultados": paginador.count,
        "filtros": {"situacao": situacao, "q": termo},
    }
    return render(request, "cupons/cupom_lista.html", contexto)


@admin_requerido
@csrf_protect
def coupon_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CouponForm(request.POST)
        if form.is_valid():
            cupom = form.save(commit=False)
            cupom.created_by = request.user
            cupom.save()
            invalidate_birthday_cache(timezone.localdate())
            _auditar(request, "cupons:cupom_criado", objeto=cupom.code)
            messages.success(request, f"Cupom {cupom.name} criado com sucesso.")
            return redirect("cupons:list")
        messages.error(request, "Nao foi possivel salvar o cupom. Verifique os campos.")
    else:
        form = CouponForm()
    return render(
        request, "cupons/cupom_form.html", {"form": form, "titulo": texto("cupons.cupom_form.titulo_novo"), "cupom": None}
    )


@admin_requerido
@csrf_protect
def coupon_update(request: HttpRequest, pk: int) -> HttpResponse:
    cupom = get_object_or_404(Coupon, pk=pk)
    if request.method == "POST":
        form = CouponForm(request.POST, instance=cupom)
        if form.is_valid():
            form.save()
            invalidate_birthday_cache(timezone.localdate())
            _auditar(request, "cupons:cupom_atualizado", objeto=cupom.code)
            messages.success(request, "Cupom atualizado com sucesso.")
            return redirect("cupons:list")
        messages.error(request, "Nao foi possivel salvar o cupom. Verifique os campos.")
    else:
        form = CouponForm(instance=cupom)
    return render(
        request,
        "cupons/cupom_form.html",
        {"form": form, "titulo": texto("cupons.cupom_form.titulo_editar", nome=cupom.name), "cupom": cupom},
    )


@admin_requerido
@csrf_protect
@require_POST
def coupon_delete(request: HttpRequest, pk: int) -> HttpResponse:
    cupom = get_object_or_404(Coupon, pk=pk)
    nome = cupom.name
    cupom.delete()
    _auditar(request, "cupons:cupom_excluido", objeto=nome)
    messages.success(request, f"Cupom {nome} excluido.")
    return redirect("cupons:list")


# ---------------------------------------------------------------------------
# Aplicacao de cupons ao cliente
# ---------------------------------------------------------------------------
@admin_requerido
@csrf_protect
@require_POST
def assignment_create(request: HttpRequest, customer_id: int) -> HttpResponse:
    """Aplica um cupom ao cliente (recorrente ou em um mes especifico)."""
    cliente = get_object_or_404(Customer, pk=customer_id)
    form = CouponAssignmentForm(
        request.POST, instance=CouponAssignment(customer=cliente)
    )
    if form.is_valid():
        try:
            aplicacao = form.save(commit=False)
            aplicacao.customer = cliente
            aplicacao.created_by = request.user
            aplicacao.save()
        except IntegrityError:
            logger.warning(
                "Aplicacao duplicada bloqueada pelo banco: cliente=%s cupom=%s",
                cliente.pk, form.cleaned_data.get("coupon"),
            )
            messages.error(request, "Este cupom ja esta aplicado a este cliente neste periodo.")
        else:
            _auditar(
                request,
                "cupons:aplicacao_criada",
                objeto=f"{aplicacao.coupon.code} -> {cliente.full_name}",
            )
            messages.success(
                request,
                f"Cupom {aplicacao.coupon.name} aplicado ({aplicacao.get_mode_display()}).",
            )
    else:
        messages.error(request, _erros_como_texto(form))

    return redirect("cupons:customer_detail", pk=cliente.pk)


@admin_requerido
@csrf_protect
@require_POST
def assignment_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove a aplicacao de um cupom (botao de excluir)."""
    aplicacao = get_object_or_404(
        CouponAssignment.objects.select_related("customer", "coupon"), pk=pk
    )
    cliente_id = aplicacao.customer_id
    descricao = f"{aplicacao.coupon.name} ({aplicacao.period_display})"
    aplicacao.delete()
    _auditar(request, "cupons:aplicacao_removida", objeto=descricao)
    messages.success(request, f"Aplicacao removida: {descricao}.")
    destino = _destino_seguro(request)
    if destino:
        return redirect(destino)
    return redirect("cupons:customer_detail", pk=cliente_id)


# ---------------------------------------------------------------------------
# Cobrancas mensais
# ---------------------------------------------------------------------------
@admin_requerido
def charge_list(request: HttpRequest) -> HttpResponse:
    """Cobrancas do mes com totais e filtro por situacao."""
    hoje = timezone.localdate()
    referencia = parse_month(request.GET.get("mes"), hoje)
    situacao = request.GET.get("situacao", "")

    cobrancas = MonthlyCharge.objects.do_mes(referencia).select_related("customer")
    if situacao in ChargeStatus.values:
        cobrancas = cobrancas.filter(status=situacao)

    totais = cobrancas.aggregate(
        mensalidades=Sum("base_amount"),
        descontos=Sum("discount_amount"),
        liquido=Sum("final_amount"),
    )

    paginador = Paginator(cobrancas.order_by("customer__full_name"), CHARGES_PER_PAGE)
    pagina = paginador.get_page(request.GET.get("page"))

    contexto = {
        "pagina": pagina,
        "totais": totais,
        "referencia": referencia,
        "referencia_label": month_label(referencia),
        "meses": month_options(hoje, back=12, forward=3),
        "filtros": {"situacao": situacao, "mes": referencia.strftime("%Y-%m")},
        "situacoes": ChargeStatus.choices,
        "total_resultados": paginador.count,
    }
    return render(request, "cupons/cobranca_lista.html", contexto)


@admin_requerido
@csrf_protect
@require_POST
def charge_generate(request: HttpRequest) -> HttpResponse:
    """Gera/atualiza as cobrancas do mes selecionado."""
    referencia = parse_month(request.POST.get("mes"), timezone.localdate())
    resumo = generate_charges(referencia)
    sync_delinquency()
    _auditar(request, "cupons:cobrancas_geradas", objeto=referencia.strftime("%Y-%m"))
    messages.success(
        request,
        "Cobrancas de {mes}: {criadas} criada(s), {atualizadas} atualizada(s), "
        "{preservadas} ja paga(s) preservada(s).".format(
            mes=month_label(referencia), **{k: v for k, v in resumo.items() if k != "mes"}
        ),
    )
    url = reverse("cupons:charge_list")
    return redirect(f"{url}?mes={referencia:%Y-%m}")


@admin_requerido
@csrf_protect
@require_POST
def charge_update_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Marca a cobranca como paga / pendente diretamente na listagem."""
    cobranca = get_object_or_404(MonthlyCharge.objects.select_related("customer"), pk=pk)
    novo_status = request.POST.get("status")
    if novo_status not in ChargeStatus.values:
        messages.error(request, "Situacao invalida.")
        return redirect("cupons:charge_list")

    cobranca.status = novo_status
    cobranca.paid_at = timezone.now() if novo_status == ChargeStatus.PAGO else None
    cobranca.save(update_fields=["status", "paid_at", "updated_at"])
    sync_delinquency(cobranca.customer)
    _auditar(
        request,
        "cupons:cobranca_situacao",
        objeto=f"{cobranca.customer.full_name}:{novo_status}",
    )
    messages.success(request, f"Cobranca de {cobranca.customer.full_name} atualizada.")
    destino = _destino_seguro(request)
    if destino:
        return redirect(destino)
    return redirect("cupons:charge_list")


@admin_requerido
@csrf_protect
def charge_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edicao completa da cobranca (situacao e vencimento)."""
    cobranca = get_object_or_404(MonthlyCharge.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        form = ChargeStatusForm(request.POST, instance=cobranca)
        if form.is_valid():
            form.save()
            sync_delinquency(cobranca.customer)
            _auditar(request, "cupons:cobranca_editada", objeto=str(cobranca))
            messages.success(request, "Cobranca atualizada com sucesso.")
            return redirect("cupons:charge_list")
        messages.error(request, _erros_como_texto(form))
    else:
        form = ChargeStatusForm(instance=cobranca)
    return render(
        request,
        "cupons/cobranca_form.html",
        {"form": form, "cobranca": cobranca, "titulo": texto("cupons.cobranca_form.titulo")},
    )


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
@admin_requerido
def cliente_lista(request: HttpRequest) -> HttpResponse:
    """Listagem paginada de clientes com busca e filtro por situacao."""
    status = request.GET.get("status", "")
    status = status if status in STATUS_VALIDOS else ""
    termo = (request.GET.get("q") or "").strip()

    clientes = (
        Customer.objects.all()
        .por_status(status)
        .buscar(termo)
        .annotate(total_aplicacoes=Count("assignments", distinct=True))
        .order_by("full_name")
    )

    paginador = Paginator(clientes, CUSTOMERS_PER_PAGE)
    pagina = paginador.get_page(request.GET.get("page"))

    contexto = {
        "pagina": pagina,
        "total_resultados": paginador.count,
        "filtros": {"status": status, "q": termo},
    }
    return render(request, "cupons/cliente_lista.html", contexto)


@admin_requerido
@csrf_protect
def customer_create(request: HttpRequest) -> HttpResponse:
    """Painel de cadastro de cliente."""
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            # O novo cliente pode fazer aniversario neste mes: refaz a checagem.
            invalidate_birthday_cache(timezone.localdate())
            _auditar(request, "cupons:cliente_criado", objeto=cliente.full_name)
            messages.success(request, f"Cliente {cliente.full_name} cadastrado com sucesso.")
            if "salvar_e_novo" in request.POST:
                return redirect("cupons:customer_create")
            return redirect("cupons:customer_detail", pk=cliente.pk)
        messages.error(request, "Nao foi possivel salvar. Verifique os campos destacados.")
    else:
        form = CustomerForm()

    return render(
        request,
        "cupons/cliente_form.html",
        {"form": form, "titulo": texto("cupons.cliente_form.titulo_novo"), "cliente": None},
    )


@admin_requerido
@csrf_protect
def customer_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edicao do cliente: abre o mesmo formulario ja preenchido."""
    cliente = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        form = CustomerForm(request.POST, instance=cliente)
        if form.is_valid():
            cliente = form.save()
            invalidate_birthday_cache(timezone.localdate())
            _auditar(request, "cupons:cliente_atualizado", objeto=cliente.full_name)
            messages.success(request, "Cliente atualizado com sucesso.")
            return redirect("cupons:customer_detail", pk=cliente.pk)
        messages.error(request, "Nao foi possivel salvar. Verifique os campos destacados.")
    else:
        form = CustomerForm(instance=cliente)

    return render(
        request,
        "cupons/cliente_form.html",
        {"form": form, "titulo": texto("cupons.cliente_form.titulo_editar", nome=cliente.full_name), "cliente": cliente},
    )


@admin_requerido
def customer_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Ficha do cliente: valor do mes (mensalidade + cupons aplicados), cupons
    vigentes, historico de aplicacoes e cobrancas.
    """
    cliente = get_object_or_404(Customer, pk=pk)
    hoje = timezone.localdate()
    referencia = parse_month(request.GET.get("mes"), hoje)

    calculo = customer_pricing(cliente, referencia)

    aplicacoes_vigentes = (
        CouponAssignment.objects.validas_no_mes(referencia)
        .filter(customer=cliente)
        .select_related("coupon")
    )
    historico = (
        CouponAssignment.objects.filter(customer=cliente)
        .select_related("coupon")
        .order_by("-start_month", "coupon__name")[:50]
    )
    cobrancas = MonthlyCharge.objects.filter(customer=cliente).order_by("-reference_month")[:12]

    contexto = {
        "cliente": cliente,
        "calculo": calculo,
        "referencia": referencia,
        "referencia_label": month_label(referencia),
        "meses": month_options(hoje, back=12, forward=3),
        "aplicacoes": aplicacoes_vigentes,
        "historico": historico,
        "cobrancas": cobrancas,
        "form_aplicacao": CouponAssignmentForm(
            instance=CouponAssignment(customer=cliente),
            initial={"start_month": referencia},
        ),
    }
    return render(request, "cupons/cliente_detalhe.html", contexto)


@admin_requerido
@csrf_protect
@require_POST
def customer_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Exclui um cliente (e, em cascata, suas aplicacoes e cobrancas)."""
    cliente = get_object_or_404(Customer, pk=pk)
    nome = cliente.full_name
    cliente.delete()
    _auditar(request, "cupons:cliente_excluido", objeto=nome)
    messages.success(request, f"Cliente {nome} excluido.")
    return redirect("cupons:cliente_lista")


@admin_requerido
@csrf_protect
@require_POST
def customer_toggle_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Ativa/desativa o cliente direto da tabela do painel."""
    cliente = get_object_or_404(Customer, pk=pk)
    cliente.is_active = not cliente.is_active
    cliente.save(update_fields=["is_active", "updated_at"])
    invalidate_birthday_cache(timezone.localdate())
    estado = "ativado" if cliente.is_active else "desativado"
    _auditar(request, "cupons:cliente_situacao", objeto=f"{cliente.full_name}:{estado}")
    messages.success(request, f"Cliente {cliente.full_name} {estado}.")
    destino = _destino_seguro(request)
    return redirect(destino or "cupons:painel")

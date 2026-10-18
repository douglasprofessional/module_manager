"""Views do módulo Kanban (adendo docs/SPEC_MODULOS.md — MÓDULO 1).

Todas exigem administrador (``is_staff``): as CBVs via ``AdminRequeridoMixin`` e
as FBVs via ``@admin_requerido`` (defesa em profundidade — o
``SomenteAdminMiddleware`` já protege o site inteiro). Toda ação que altera
dados usa ``@csrf_protect`` + ``@require_POST`` e registra auditoria.

- ``QuadroListView``: lista de quadros não arquivados com contadores.
- ``QuadroDetailView``: o board (colunas + cartões), com dados de vizinhança
  para os botões de mover (fallback sem JS).
- ``novo_quadro``: cria um ``Quadro`` e redireciona para o board novo.
- ``nova_coluna`` / ``novo_cartao``: criam coluna/cartão ao final da ordem.
- ``mover_cartao``: move um cartão para outra coluna do MESMO quadro.
- ``alternar_concluido``: inverte o estado de conclusão de um cartão.

As ações POST respondem JSON quando chamadas via AJAX (cabeçalho
``X-Requested-With``) e, caso contrário, redirecionam ao board (degrada sem JS).
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.db.models import Count, Max, Prefetch, Q, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView

from apps.contas.decorators import admin_requerido
from apps.contas.mixins import AdminRequeridoMixin
from apps.kanban.forms import CartaoForm, ColunaForm, QuadroForm
from apps.kanban.models import Cartao, Coluna, Quadro

logger = logging.getLogger("modulos.kanban.views")


def _ip(request: HttpRequest) -> str | None:
    """IP do cliente (REMOTE_ADDR); não confia em cabeçalhos de proxy."""
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
    except Exception:  # auditoria é best-effort
        logger.exception("Falha ao registrar auditoria (acao=%s).", acao)


def _e_ajax(request: HttpRequest) -> bool:
    """Detecta requisição assíncrona pelo cabeçalho ``X-Requested-With``."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


class QuadroListView(AdminRequeridoMixin, ListView):
    """Lista de quadros não arquivados, com contadores por quadro."""

    model = Quadro
    template_name = "kanban/lista.html"
    context_object_name = "quadros"

    def get_queryset(self) -> QuerySet[Quadro]:
        hoje = timezone.localdate()
        return (
            Quadro.objects.filter(arquivado=False)
            .annotate(
                num_colunas=Count("colunas", distinct=True),
                num_cartoes=Count("colunas__cartoes", distinct=True),
                num_atrasados=Count(
                    "colunas__cartoes",
                    filter=Q(
                        colunas__cartoes__concluido=False,
                        colunas__cartoes__prazo__lt=hoje,
                    ),
                    distinct=True,
                ),
            )
            .order_by("-criado_em")
        )


class QuadroDetailView(AdminRequeridoMixin, DetailView):
    """O board de um quadro: colunas em ordem, cada uma com seus cartões."""

    model = Quadro
    template_name = "kanban/quadro.html"
    context_object_name = "quadro"

    def get_queryset(self) -> QuerySet[Quadro]:
        cartoes = Cartao.objects.select_related("responsavel").order_by("ordem", "id")
        return Quadro.objects.prefetch_related(
            Prefetch("colunas", queryset=Coluna.objects.order_by("ordem", "id")),
            Prefetch("colunas__cartoes", queryset=cartoes),
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        colunas = list(self.object.colunas.all())  # já pré-carregadas e ordenadas
        total = len(colunas)
        lista_colunas = []
        for i, coluna in enumerate(colunas):
            cartoes = list(coluna.cartoes.all())  # do cache de prefetch (sem query)
            # WIP calculado a partir do prefetch para evitar COUNT por coluna (N+1).
            estourou = coluna.limite_wip is not None and len(cartoes) > coluna.limite_wip
            lista_colunas.append(
                {
                    "coluna": coluna,
                    "cartoes": cartoes,
                    "total_cartoes": len(cartoes),
                    "estourou_wip": estourou,
                    "anterior_id": colunas[i - 1].id if i > 0 else None,
                    "proximo_id": colunas[i + 1].id if i < total - 1 else None,
                }
            )
        contexto["colunas"] = lista_colunas
        contexto["form_coluna"] = ColunaForm()
        contexto["form_cartao"] = CartaoForm()
        contexto["opcoes_prioridade"] = Cartao.Prioridade.choices
        return contexto


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def novo_quadro(request: HttpRequest) -> HttpResponse:
    """Cria um novo quadro e leva ao board recém-criado."""
    if request.method == "POST":
        form = QuadroForm(request.POST)
        if form.is_valid():
            quadro = form.save(commit=False)
            quadro.criado_por = request.user
            quadro.save()
            _auditar(request, "kanban:quadro_criado", objeto=quadro.nome)
            messages.success(request, _("Quadro criado com sucesso."), fail_silently=True)
            return redirect("kanban:quadro", pk=quadro.pk)
    else:
        form = QuadroForm()

    return render(request, "kanban/novo_quadro.html", {"form": form})


@admin_requerido
@csrf_protect
@require_POST
def nova_coluna(request: HttpRequest, pk: int) -> HttpResponse:
    """Cria uma coluna no quadro (``pk``), ao final da ordem existente."""
    quadro = get_object_or_404(Quadro, pk=pk)
    form = ColunaForm(request.POST)
    if form.is_valid():
        coluna = form.save(commit=False)
        coluna.quadro = quadro
        proxima = quadro.colunas.aggregate(m=Max("ordem")).get("m")
        coluna.ordem = (proxima or 0) + 1
        coluna.save()
        _auditar(request, "kanban:coluna_criada", objeto=str(coluna))
        messages.success(request, _("Coluna criada."), fail_silently=True)
    else:
        messages.error(request, _("Não foi possível criar a coluna."), fail_silently=True)
    return redirect("kanban:quadro", pk=quadro.pk)


@admin_requerido
@csrf_protect
@require_POST
def novo_cartao(request: HttpRequest, pk: int) -> HttpResponse:
    """Cria um cartão na coluna (``pk``), ao final da ordem existente."""
    coluna = get_object_or_404(Coluna.objects.select_related("quadro"), pk=pk)
    form = CartaoForm(request.POST)
    if form.is_valid():
        cartao = form.save(commit=False)
        cartao.coluna = coluna
        cartao.criado_por = request.user
        proxima = coluna.cartoes.aggregate(m=Max("ordem")).get("m")
        cartao.ordem = (proxima or 0) + 1
        cartao.save()
        _auditar(request, "kanban:cartao_criado", objeto=cartao.titulo)
        messages.success(request, _("Cartão adicionado."), fail_silently=True)
    else:
        messages.error(request, _("Não foi possível adicionar o cartão."), fail_silently=True)
    return redirect("kanban:quadro", pk=coluna.quadro_id)


@admin_requerido
@csrf_protect
@require_POST
def mover_cartao(request: HttpRequest, pk: int) -> HttpResponse:
    """Move um cartão para outra coluna do MESMO quadro.

    Espera ``coluna_destino`` (id) e, opcionalmente, ``ordem``. Valida a
    existência da coluna de destino e que ela pertence ao mesmo quadro do
    cartão (nunca confia em ids arbitrários). Responde JSON via AJAX; caso
    contrário, redireciona ao board.
    """
    cartao = get_object_or_404(
        Cartao.objects.select_related("coluna", "coluna__quadro"), pk=pk
    )
    quadro_id = cartao.coluna.quadro_id

    # Valida o id antes do lookup: pk não-numérico faria o ORM levantar
    # ValueError (não capturado por get_object_or_404), virando HTTP 500.
    destino_id = (request.POST.get("coluna_destino") or "").strip()
    if not destino_id.isdigit():
        if _e_ajax(request):
            return JsonResponse({"ok": False, "erro": "coluna_destino inválida"}, status=400)
        messages.error(request, _("Coluna de destino inválida."), fail_silently=True)
        return redirect("kanban:quadro", pk=quadro_id)

    coluna_destino = get_object_or_404(
        Coluna.objects.select_related("quadro"),
        pk=int(destino_id),
        quadro_id=quadro_id,
    )

    cartao.coluna = coluna_destino
    ordem_bruta = (request.POST.get("ordem") or "").strip()
    if ordem_bruta.isdigit():
        cartao.ordem = int(ordem_bruta)
    else:
        proxima = coluna_destino.cartoes.aggregate(m=Max("ordem")).get("m")
        cartao.ordem = (proxima or 0) + 1
    cartao.save(update_fields=["coluna", "ordem", "atualizado_em"])
    _auditar(
        request,
        "kanban:cartao_movido",
        objeto=f"{cartao.titulo} → {coluna_destino.nome}",
    )

    if _e_ajax(request):
        return JsonResponse({"ok": True})
    return redirect("kanban:quadro", pk=quadro_id)


@admin_requerido
@csrf_protect
@require_POST
def alternar_concluido(request: HttpRequest, pk: int) -> HttpResponse:
    """Inverte o estado de conclusão de um cartão. Responde JSON via AJAX."""
    cartao = get_object_or_404(
        Cartao.objects.select_related("coluna", "coluna__quadro"), pk=pk
    )
    cartao.concluido = not cartao.concluido
    cartao.save(update_fields=["concluido", "atualizado_em"])
    _auditar(
        request,
        "kanban:cartao_concluido" if cartao.concluido else "kanban:cartao_reaberto",
        objeto=cartao.titulo,
    )

    if _e_ajax(request):
        return JsonResponse({"ok": True, "concluido": cartao.concluido})
    return redirect("kanban:quadro", pk=cartao.coluna.quadro_id)

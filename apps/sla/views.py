"""Views do módulo de SLA (adendo docs/SPEC_MODULOS.md — MÓDULO 2).

Todas exigem administrador (``is_staff``): as CBVs via ``AdminRequeridoMixin`` e
as FBVs via ``@admin_requerido``. Além disso, o ``SomenteAdminMiddleware`` já
protege o site inteiro (defesa em profundidade). As ações POST são protegidas
por ``@csrf_protect`` e restritas ao método correto.

- ``ChamadoListView``: tabela paginada com filtros por ``status`` (ORM) e por
  ``situacao`` de SLA (em_risco/estourado, calculada em Python).
- ``ChamadoDetailView``: ficha do chamado com situações, percentuais e textos.
- ``novo_chamado``: cria um chamado (os prazos são calculados no ``save()``).
- ``politicas``: lista e cria políticas de SLA.
- ``registrar_resposta`` / ``resolver``: marcos de atendimento (POST/CSRF).
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView

from apps.contas.decorators import admin_requerido
from apps.contas.mixins import AdminRequeridoMixin
from apps.sla.forms import ChamadoForm, PoliticaForm
from apps.sla.models import (
    ROTULOS_SITUACAO,
    SIT_EM_RISCO,
    SIT_ESTOURADO,
    Chamado,
    Politica,
)

logger = logging.getLogger("modulos.sla.views")

# Filtros de situação aplicados em Python (dependem de cálculo de SLA).
# Reutiliza os rótulos (lazy) definidos no modelo para manter consistência.
OPCOES_SITUACAO: list[tuple[str, Any]] = [
    (SIT_EM_RISCO, ROTULOS_SITUACAO[SIT_EM_RISCO]),
    (SIT_ESTOURADO, ROTULOS_SITUACAO[SIT_ESTOURADO]),
]
SITUACOES_FILTRAVEIS = {SIT_EM_RISCO, SIT_ESTOURADO}


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


class ChamadoListView(AdminRequeridoMixin, ListView):
    """Lista paginada de chamados com filtros por status e situação de SLA."""

    model = Chamado
    template_name = "sla/lista.html"
    context_object_name = "chamados"
    paginate_by = 20

    def get_queryset(self):
        queryset = Chamado.objects.select_related("politica", "responsavel")

        status = (self.request.GET.get("status") or "").strip()
        if status in Chamado.Status.values:
            queryset = queryset.filter(status=status)

        queryset = queryset.order_by("-aberto_em")

        # A situação de SLA depende de cálculo (prazos + agora): filtra em Python.
        situacao = (self.request.GET.get("situacao") or "").strip()
        if situacao in SITUACOES_FILTRAVEIS:
            return [c for c in queryset if c.situacao_resolucao() == situacao]
        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        contexto["filtro_status"] = self.request.GET.get("status", "")
        contexto["filtro_situacao"] = self.request.GET.get("situacao", "")
        contexto["opcoes_status"] = Chamado.Status.choices
        contexto["opcoes_situacao"] = OPCOES_SITUACAO
        contexto["querystring_filtros"] = self._querystring_sem_pagina()
        return contexto

    def _querystring_sem_pagina(self) -> str:
        """Querystring atual (sem 'page') para preservar filtros na paginação."""
        parametros = {
            chave: valor
            for chave, valor in self.request.GET.items()
            if chave != "page" and valor
        }
        return urlencode(parametros)


class ChamadoDetailView(AdminRequeridoMixin, DetailView):
    """Ficha completa de um chamado, com dados de SLA calculados."""

    template_name = "sla/detalhe.html"
    context_object_name = "chamado"

    def get_queryset(self) -> QuerySet[Chamado]:
        return Chamado.objects.select_related("politica", "responsavel")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        chamado: Chamado = self.object
        sit_resolucao = chamado.situacao_resolucao()
        sit_resposta = chamado.situacao_resposta()
        contexto.update(
            {
                "situacao_resolucao": sit_resolucao,
                "situacao_resposta": sit_resposta,
                "classe_resolucao": chamado.classe_situacao(sit_resolucao),
                "classe_resposta": chamado.classe_situacao(sit_resposta),
                "rotulo_resolucao": chamado.rotulo_situacao(sit_resolucao),
                "rotulo_resposta": chamado.rotulo_situacao(sit_resposta),
                "percentual_resolucao": chamado.percentual_resolucao(),
                "tempo_restante": chamado.tempo_restante_texto(),
            }
        )
        return contexto


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def novo_chamado(request: HttpRequest) -> HttpResponse:
    """Cria um novo chamado. Os prazos de SLA são calculados no ``save()``."""
    if request.method == "POST":
        form = ChamadoForm(request.POST)
        if form.is_valid():
            chamado = form.save(commit=False)
            chamado.criado_por = request.user
            chamado.save()  # calcula prazo_resposta/prazo_resolucao
            _auditar(request, "sla:chamado_criado", objeto=str(chamado))
            messages.success(request, _("Chamado criado com sucesso."), fail_silently=True)
            return redirect("sla:detalhe", pk=chamado.pk)
    else:
        form = ChamadoForm()

    return render(request, "sla/novo_chamado.html", {"form": form})


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def politicas(request: HttpRequest) -> HttpResponse:
    """Lista as políticas de SLA e permite criar novas."""
    if request.method == "POST":
        form = PoliticaForm(request.POST)
        if form.is_valid():
            politica = form.save()
            _auditar(request, "sla:politica_criada", objeto=politica.nome)
            messages.success(request, _("Política criada com sucesso."), fail_silently=True)
            return redirect("sla:politicas")
    else:
        form = PoliticaForm()

    contexto = {
        "form": form,
        "politicas": Politica.objects.annotate(total_chamados=Count("chamados")),
    }
    return render(request, "sla/politicas.html", contexto)


@admin_requerido
@csrf_protect
@require_POST
def registrar_resposta(request: HttpRequest, pk: int) -> HttpResponse:
    """Marca a primeira resposta e coloca o chamado em andamento."""
    chamado = get_object_or_404(
        Chamado.objects.select_related("politica"), pk=pk
    )
    if chamado.primeira_resposta_em is None:
        chamado.primeira_resposta_em = timezone.now()
    # Não regride chamados já resolvidos/fechados.
    if chamado.status in (Chamado.Status.ABERTO, Chamado.Status.PAUSADO):
        chamado.status = Chamado.Status.EM_ANDAMENTO
    chamado.save()
    _auditar(request, "sla:resposta_registrada", objeto=str(chamado))
    messages.success(request, _("Resposta registrada."), fail_silently=True)
    return redirect("sla:detalhe", pk=chamado.pk)


@admin_requerido
@csrf_protect
@require_POST
def resolver(request: HttpRequest, pk: int) -> HttpResponse:
    """Marca o chamado como resolvido (registrando o instante da resolução)."""
    chamado = get_object_or_404(
        Chamado.objects.select_related("politica"), pk=pk
    )
    agora = timezone.now()
    if chamado.primeira_resposta_em is None:
        # Resolver implica que houve atendimento: registra também a 1ª resposta.
        chamado.primeira_resposta_em = agora
    if chamado.resolvido_em is None:
        chamado.resolvido_em = agora
    # Não regride estados terminais (FECHADO) nem reescreve um já RESOLVIDO.
    if chamado.status not in (Chamado.Status.RESOLVIDO, Chamado.Status.FECHADO):
        chamado.status = Chamado.Status.RESOLVIDO
    chamado.save()
    _auditar(request, "sla:chamado_resolvido", objeto=str(chamado))
    messages.success(request, _("Chamado marcado como resolvido."), fail_silently=True)
    return redirect("sla:detalhe", pk=chamado.pk)

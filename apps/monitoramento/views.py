"""Views do módulo de Monitoramento (adendo 2 — MÓDULO 3).

Todas exigem administrador (``is_staff``): as CBVs via ``AdminRequeridoMixin`` e
as FBVs via ``@admin_requerido`` (defesa em profundidade — o
``SomenteAdminMiddleware`` já protege o site inteiro). Toda ação que altera
dados usa ``@csrf_protect`` + ``@require_POST`` e registra auditoria.

- ``ServidorListView``: grid (estilo Proxmox) dos servidores com a última leitura
  (medidores de CPU/RAM/disco).
- ``ServidorDetailView``: última leitura + histórico (mini-gráfico) + tabela.
- ``novo`` / ``editar``: criam/editam servidor (segredos cifrados; em branco = manter).
- ``coletar`` (POST): coleta métricas de UM servidor (TOFU do fingerprint).
- ``coletar_todos`` (POST): coleta de todos os servidores ativos (com teto).
- ``excluir`` (POST): remove o servidor (e leituras por cascade).

As ações POST respondem JSON quando chamadas via AJAX (``X-Requested-With``);
caso contrário, redirecionam com ``messages`` (degrada sem JS). Os segredos
NUNCA aparecem em JSON, log ou mensagem.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.db.models import Max, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView

from apps.contas.decorators import admin_requerido
from apps.contas.mixins import AdminRequeridoMixin
from apps.monitoramento.forms import ServidorForm
from apps.monitoramento.models import LeituraMetrica, ServidorVPS

logger = logging.getLogger("modulos.monitoramento.views")

# Teto de servidores processados por 'coletar_todos' (evita coletas gigantes
# síncronas). Ajustável se a operação migrar para tarefa assíncrona.
TETO_COLETAR_TODOS = 50

# Nº de leituras usadas no mini-gráfico e na tabela do detalhe.
HISTORICO_LIMITE = 30

# Retenção: nº máximo de leituras mantidas por servidor (o histórico é podado a
# cada coleta para não crescer sem limite).
RETENCAO_LEITURAS = 500

# Campos de métrica copiados do resultado da coleta para a LeituraMetrica.
CAMPOS_METRICA = (
    "cpu_pct",
    "mem_pct",
    "mem_total_mb",
    "mem_usada_mb",
    "disco_pct",
    "disco_total_gb",
    "disco_usado_gb",
    "uptime_segundos",
    "carga1",
    "carga5",
    "carga15",
    "nucleos",
)


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


def _status_da_coleta(resultado: dict) -> str:
    """Deriva o ``ultimo_status`` do servidor a partir do resultado da coleta.

    - online          -> ONLINE
    - falha de conexão -> OFFLINE (host inacessível / timeout)
    - demais falhas    -> ERRO (auth, host key mudou, paramiko ausente, parse…)
    """
    if resultado.get("online"):
        return ServidorVPS.Status.ONLINE
    erro = (resultado.get("erro") or "").lower()
    indicadores_offline = ("conectar", "conexão", "esgotado", "host/porta")
    if any(ind in erro for ind in indicadores_offline):
        return ServidorVPS.Status.OFFLINE
    return ServidorVPS.Status.ERRO


def _leitura_para_medidores(leitura: LeituraMetrica | None, servidor: ServidorVPS) -> dict:
    """Monta os dados de medidores (pct + cor) para um cartão da lista.

    As cores são calculadas em Python (``cor_uso`` recebe argumento e não pode
    ser chamada no template).
    """
    def medidor(pct):
        return {
            "pct": pct,
            "cor": servidor.cor_uso(pct),
            "largura": max(0, min(100, round(pct))) if pct is not None else 0,
        }

    if leitura is None:
        return {
            "leitura": None,
            "cpu": medidor(None),
            "mem": medidor(None),
            "disco": medidor(None),
        }
    return {
        "leitura": leitura,
        "cpu": medidor(leitura.cpu_pct),
        "mem": medidor(leitura.mem_pct),
        "disco": medidor(leitura.disco_pct),
    }


def _ultimas_leituras(servidor_ids: list[int]) -> dict[int, LeituraMetrica]:
    """Retorna a leitura mais recente por servidor, sem materializar a tabela.

    Busca no banco apenas o maior ``pk`` (= leitura mais recente, pois o ``pk`` é
    crescente) por servidor e depois carrega só essas linhas. O custo é
    O(nº de servidores), não O(total de leituras) — importante porque
    ``LeituraMetrica`` cresce a cada coleta. Portável (SQLite/PostgreSQL).
    """
    if not servidor_ids:
        return {}
    ultimas_pks = (
        LeituraMetrica.objects.filter(servidor_id__in=servidor_ids)
        .values("servidor_id")
        .annotate(ultima=Max("pk"))
        .values_list("ultima", flat=True)
    )
    leituras = LeituraMetrica.objects.filter(pk__in=list(ultimas_pks))
    return {leitura.servidor_id: leitura for leitura in leituras}


def _podar_historico(servidor: ServidorVPS) -> None:
    """Mantém apenas as últimas ``RETENCAO_LEITURAS`` leituras do servidor.

    É best-effort: uma falha na poda nunca interrompe a coleta.
    """
    try:
        ids_manter = list(
            LeituraMetrica.objects.filter(servidor=servidor)
            .order_by("-coletado_em", "-id")
            .values_list("pk", flat=True)[:RETENCAO_LEITURAS]
        )
        if len(ids_manter) >= RETENCAO_LEITURAS:
            LeituraMetrica.objects.filter(servidor=servidor).exclude(
                pk__in=ids_manter
            ).delete()
    except Exception:  # pragma: no cover - poda é secundária à coleta
        logger.warning("Falha ao podar o histórico do servidor %s.", servidor.pk, exc_info=True)


class ServidorListView(AdminRequeridoMixin, ListView):
    """Grid de servidores (ativos e inativos) com a última leitura por servidor."""

    model = ServidorVPS
    template_name = "monitoramento/lista.html"
    context_object_name = "servidores"

    def get_queryset(self) -> QuerySet[ServidorVPS]:
        return ServidorVPS.objects.all().order_by("nome")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        servidores = list(contexto.get("servidores") or [])
        ultimas = _ultimas_leituras([s.pk for s in servidores])

        cartoes = []
        for servidor in servidores:
            leitura = ultimas.get(servidor.pk)
            dados = _leitura_para_medidores(leitura, servidor)
            dados["servidor"] = servidor
            cartoes.append(dados)

        contexto["cartoes"] = cartoes
        contexto["total"] = len(servidores)
        return contexto


class ServidorDetailView(AdminRequeridoMixin, DetailView):
    """Ficha do servidor: última leitura + histórico (mini-gráfico) + tabela."""

    model = ServidorVPS
    template_name = "monitoramento/detalhe.html"
    context_object_name = "servidor"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        servidor: ServidorVPS = self.object

        # Histórico recente (mais novo primeiro para a tabela).
        historico = list(servidor.leituras.all()[:HISTORICO_LIMITE])
        ultima = historico[0] if historico else None

        # Série cronológica (mais antigo -> mais novo) para o mini-gráfico.
        cronologico = list(reversed(historico))
        # None vira 0 para não invalidar a série inteira em pontos_polyline.
        serie_cpu = [round(l.cpu_pct or 0, 1) for l in cronologico]
        serie_mem = [round(l.mem_pct or 0, 1) for l in cronologico]
        serie_disco = [round(l.disco_pct or 0, 1) for l in cronologico]

        contexto["ultima"] = ultima
        contexto["historico"] = historico
        contexto["serie_cpu"] = serie_cpu
        contexto["serie_mem"] = serie_mem
        contexto["serie_disco"] = serie_disco
        contexto["tem_grafico"] = len(cronologico) >= 2
        if ultima is not None:
            contexto["medidores"] = _leitura_para_medidores(ultima, servidor)
        else:
            contexto["medidores"] = _leitura_para_medidores(None, servidor)
        return contexto


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def novo(request: HttpRequest) -> HttpResponse:
    """Cria um novo servidor (não exige coleta) e leva à ficha recém-criada."""
    if request.method == "POST":
        form = ServidorForm(request.POST)
        if form.is_valid():
            servidor = form.save(commit=False)
            servidor.criado_por = request.user
            servidor.save()
            _auditar(request, "monitoramento:servidor_criado", objeto=str(servidor))
            messages.success(request, _("Servidor cadastrado com sucesso."), fail_silently=True)
            return redirect("monitoramento:detalhe", pk=servidor.pk)
    else:
        form = ServidorForm()

    contexto = {"form": form, "modo": "novo"}
    return render(request, "monitoramento/form.html", contexto)


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def editar(request: HttpRequest, pk: int) -> HttpResponse:
    """Edita um servidor. Segredos em branco = manter; permite resetar host key."""
    servidor = get_object_or_404(ServidorVPS, pk=pk)
    if request.method == "POST":
        form = ServidorForm(request.POST, instance=servidor)
        if form.is_valid():
            servidor = form.save()
            _auditar(request, "monitoramento:servidor_editado", objeto=str(servidor))
            messages.success(request, _("Servidor atualizado com sucesso."), fail_silently=True)
            return redirect("monitoramento:detalhe", pk=servidor.pk)
    else:
        form = ServidorForm(instance=servidor)

    contexto = {"form": form, "modo": "editar", "servidor": servidor}
    return render(request, "monitoramento/form.html", contexto)


def _coletar_servidor(request: HttpRequest, servidor: ServidorVPS) -> dict:
    """Coleta as métricas de um servidor, persiste a leitura e atualiza o status.

    Retorna um dict SEGURO (sem segredos) útil para a resposta JSON.
    """
    from apps.monitoramento.services import ssh_coletor

    resultado = ssh_coletor.coletar_metricas(servidor)

    # Cria a leitura histórica com os campos de métrica do resultado.
    leitura = LeituraMetrica(
        servidor=servidor,
        online=bool(resultado.get("online")),
        sistema=(resultado.get("sistema") or "")[:200],
        erro=(resultado.get("erro") or ""),
    )
    for campo in CAMPOS_METRICA:
        setattr(leitura, campo, resultado.get(campo))
    leitura.save()
    _podar_historico(servidor)  # mantém o histórico limitado

    # Atualiza o status/última coleta e aprende o fingerprint (TOFU) se veio novo
    # e o campo estava vazio.
    status = _status_da_coleta(resultado)
    servidor.ultimo_status = status
    servidor.ultima_coleta_em = timezone.now()
    campos_update = ["ultimo_status", "ultima_coleta_em", "atualizado_em"]

    fingerprint_novo = resultado.get("fingerprint_novo")
    if fingerprint_novo and not (servidor.host_key_fingerprint or "").strip():
        servidor.host_key_fingerprint = fingerprint_novo
        campos_update.append("host_key_fingerprint")

    servidor.save(update_fields=campos_update)

    return {
        "ok": True,
        "online": leitura.online,
        "status": status,
        "status_rotulo": servidor.get_ultimo_status_display(),
        "classe_status": servidor.classe_status(),
        "cpu_pct": leitura.cpu_pct,
        "mem_pct": leitura.mem_pct,
        "disco_pct": leitura.disco_pct,
        "erro": leitura.erro,
    }


@admin_requerido
@csrf_protect
@require_POST
def coletar(request: HttpRequest, pk: int) -> HttpResponse:
    """Coleta as métricas de UM servidor (POST). Responde JSON via AJAX."""
    servidor = get_object_or_404(ServidorVPS, pk=pk)
    try:
        dados = _coletar_servidor(request, servidor)
    except Exception:
        logger.exception("Falha inesperada ao coletar o servidor %s.", servidor.pk)
        _auditar(request, "monitoramento:coleta_falhou", objeto=str(servidor))
        if _e_ajax(request):
            return JsonResponse({"ok": False, "erro": "falha na coleta"}, status=500)
        messages.error(request, _("Não foi possível coletar as métricas."), fail_silently=True)
        return redirect("monitoramento:detalhe", pk=servidor.pk)

    _auditar(request, "monitoramento:coleta", objeto=f"{servidor} [{dados['status']}]")

    if _e_ajax(request):
        return JsonResponse(dados)

    if dados["online"]:
        messages.success(request, _("Coleta concluída: servidor online."), fail_silently=True)
    else:
        messages.warning(
            request,
            _("Coleta concluída: %(erro)s.") % {"erro": dados["erro"] or _("servidor indisponível")},
            fail_silently=True,
        )
    return redirect("monitoramento:detalhe", pk=servidor.pk)


@admin_requerido
@csrf_protect
@require_POST
def coletar_todos(request: HttpRequest) -> HttpResponse:
    """Coleta as métricas de todos os servidores ativos (com teto). Resiliente."""
    servidores = list(
        ServidorVPS.objects.filter(ativo=True).order_by("nome")[:TETO_COLETAR_TODOS]
    )
    online = 0
    falhas = 0
    for servidor in servidores:
        try:
            dados = _coletar_servidor(request, servidor)
            if dados["online"]:
                online += 1
            else:
                falhas += 1
        except Exception:  # resiliente por servidor
            logger.exception("Falha ao coletar o servidor %s em coletar_todos.", servidor.pk)
            falhas += 1

    _auditar(
        request,
        "monitoramento:coleta_todos",
        objeto=f"{len(servidores)} servidor(es): {online} online, {falhas} com falha",
    )
    messages.success(
        request,
        _("Coleta concluída: %(online)d online, %(falhas)d com falha.")
        % {"online": online, "falhas": falhas},
        fail_silently=True,
    )
    return redirect("monitoramento:lista")


@admin_requerido
@csrf_protect
@require_POST
def excluir(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove o servidor (e suas leituras por cascade). Auditoria."""
    servidor = get_object_or_404(ServidorVPS, pk=pk)
    rotulo = str(servidor)
    servidor.delete()
    _auditar(request, "monitoramento:servidor_excluido", objeto=rotulo)
    messages.success(request, _("Servidor removido."), fail_silently=True)
    return redirect("monitoramento:lista")

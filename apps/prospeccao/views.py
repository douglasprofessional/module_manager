"""Views do módulo de prospecção (seção 13 da SPEC).

Todas exigem administrador (``is_staff``): as CBVs via
``AdminRequeridoMixin`` e as FBVs via ``@admin_requerido``. Além disso, o
``SomenteAdminMiddleware`` já protege o site inteiro.

- ``painel``: dashboard do módulo — métricas da Google Places API (New), campo
  para colar/salvar/testar a chave do Google, configuração da IA e critérios
  do motor de análise (com recálculo).
- ``EmpresaListView``: tabela paginada com filtros por ``status`` e ``problema``.
- ``EmpresaDetailView``: ficha completa (site, perfil no Google e diagnósticos).
- ``atualizar_google``: POST que consulta o Place Details e reanalisa a empresa.
- ``diagnostico_ia``: POST que gera o diagnóstico em texto com a IA (Claude).
- ``conexoes``: lista e cria ``ConexaoGoogle`` (chave salva cifrada).
- ``nova_busca``: cria uma ``Busca`` (não executa).
- ``executar_busca``: POST/CSRF que dispara a task síncrona de execução.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView

from apps.contas.decorators import admin_requerido
from apps.contas.mixins import AdminRequeridoMixin
from apps.nucleo.textos import texto
from apps.prospeccao.forms import (
    BuscaForm,
    ChaveGoogleForm,
    ConexaoGoogleForm,
    IAForm,
    LimiaresForm,
)
from apps.prospeccao.models import (
    PROBLEMAS,
    Busca,
    ConexaoGoogle,
    ConfiguracaoProspeccao,
    Empresa,
    filtros_problema,
    rotulo_problema,
)
from apps.prospeccao.services import credenciais
from apps.prospeccao.services.analise_places import (
    HORARIO_AUSENTE,
    HORARIO_INCOMPLETO,
    HORARIO_OK,
    STATUS_FECHADA_PERMANENTEMENTE,
    STATUS_FECHADA_TEMPORARIAMENTE,
    STATUS_OPERACIONAL,
)

logger = logging.getLogger("modulos.prospeccao.views")

_P = "prospeccao.painel."
_D = "prospeccao.detalhe."


def _filtros_extras() -> dict[str, tuple[str, Q]]:
    """Filtros do Painel sem badge próprio: slug -> (rótulo, expressão ORM)."""
    analisada = Q(analisado_places_em__isnull=False)
    return {
        "sem_website": (texto(_P + "metrica_sem_site"), analisada & Q(website="")),
        "horario_irregular": (
            texto(_P + "metrica_horario"),
            Q(situacao_horario__in=[HORARIO_AUSENTE, HORARIO_INCOMPLETO]),
        ),
    }


def _filtro_por_slug(slug: str, config: ConfiguracaoProspeccao) -> Q | None:
    """Expressão ORM do filtro ``problema`` da querystring (ou ``None``)."""
    filtro = filtros_problema(config).get(slug)
    if filtro is not None:
        return filtro
    extra = _filtros_extras().get(slug)
    return extra[1] if extra else None


def _opcoes_problema() -> list[tuple[str, str]]:
    """Opções (slug, rótulo) do seletor de problema da lista de empresas."""
    opcoes = [(slug, rotulo_problema(slug)) for slug in PROBLEMAS]
    opcoes += [(slug, rotulo) for slug, (rotulo, _q) in _filtros_extras().items()]
    return opcoes


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


def _config_do_banco() -> ConfiguracaoProspeccao:
    """Singleton lido direto do banco (evita sobrescrever com cópia em cache)."""
    try:
        config, _criado = ConfiguracaoProspeccao.objects.get_or_create(pk=1)
        return config
    except Exception:
        logger.exception("Falha ao ler a configuração da prospecção; usando padrões.")
        return ConfiguracaoProspeccao(pk=1)


# ---------------------------------------------------------------------------
# Painel do módulo
# ---------------------------------------------------------------------------
def _metricas_google(config: ConfiguracaoProspeccao) -> dict[str, Any]:
    """Indicadores do motor de análise sobre as empresas analisadas no Google."""
    filtros = filtros_problema(config)
    extras = _filtros_extras()
    definicoes = [
        ("nota_baixa", texto(_P + "metrica_nota_baixa", nota=f"{config.limiar_nota:.1f}".replace(".", ",")), filtros["nota_baixa"], "vermelho"),
        ("sem_website", extras["sem_website"][0], extras["sem_website"][1], "vermelho"),
        ("poucas_avaliacoes", texto(_P + "metrica_poucas_avaliacoes", quantidade=config.limiar_avaliacoes), filtros["poucas_avaliacoes"], "amarelo"),
        ("horario_irregular", extras["horario_irregular"][0], extras["horario_irregular"][1], "amarelo"),
        ("fechada", texto(_P + "metrica_fechadas"), filtros["fechada"], "vermelho"),
        ("poucas_fotos", texto(_P + "metrica_poucas_fotos", quantidade=config.limiar_fotos), filtros["poucas_fotos"], "azul"),
        ("perfil_desatualizado", texto(_P + "metrica_desatualizado", meses=config.limiar_meses), filtros["perfil_desatualizado"], "roxo"),
    ]
    base = Empresa.objects.filter(analisado_places_em__isnull=False)
    agregados = {"total": Count("pk")}
    for slug, _rotulo, filtro, _cor in definicoes:
        agregados[slug] = Count("pk", filter=filtro)
    try:
        valores = base.aggregate(**agregados)
    except Exception:
        logger.exception("Falha ao calcular as métricas do Google.")
        valores = {}
    total = int(valores.get("total") or 0)
    url_lista = reverse("prospeccao:lista")
    cards = []
    for slug, rotulo, _filtro, cor in definicoes:
        quantidade = int(valores.get(slug) or 0)
        cards.append(
            {
                "slug": slug,
                "rotulo": rotulo,
                "valor": quantidade,
                "pct": round(quantidade / total * 100) if total else 0,
                "cor": cor,
                "url": f"{url_lista}?{urlencode({'problema': slug})}",
            }
        )
    return {"total": total, "cards": cards}


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def painel(request: HttpRequest) -> HttpResponse:
    """Dashboard do módulo: métricas, chave do Google, IA e critérios."""
    config = _config_do_banco()
    form_chave = ChaveGoogleForm(configurada=config.tem_chave_google)
    form_ia = IAForm(instance=config)
    form_limiares = LimiaresForm(instance=config)

    if request.method == "POST":
        acao = (request.POST.get("acao") or "").strip()
        destino = redirect("prospeccao:painel")

        if acao == "salvar_chave_google":
            form_chave = ChaveGoogleForm(request.POST, configurada=config.tem_chave_google)
            if form_chave.is_valid():
                form_chave.salvar(config)
                _auditar(request, "prospeccao:chave_google_salva")
                messages.success(request, texto(_P + "msg_chave_salva"), fail_silently=True)
                return destino
            messages.error(request, texto(_P + "msg_form_invalido"), fail_silently=True)

        elif acao == "remover_chave_google":
            config.chave_google = ""
            config.save()
            _auditar(request, "prospeccao:chave_google_removida")
            messages.success(request, texto(_P + "msg_chave_removida"), fail_silently=True)
            return destino

        elif acao == "testar_chave_google":
            from apps.prospeccao.services import google_places

            try:
                google_places.testar_chave(credenciais.chave_google())
            except google_places.ErroConfiguracao as exc:
                messages.error(request, texto(_P + "msg_chave_erro", erro=str(exc)), fail_silently=True)
            else:
                messages.success(request, texto(_P + "msg_chave_ok"), fail_silently=True)
            return destino

        elif acao == "salvar_ia":
            form_ia = IAForm(request.POST, instance=config)
            if form_ia.is_valid():
                form_ia.save()
                _auditar(request, "prospeccao:ia_configurada")
                messages.success(request, texto(_P + "msg_ia_salva"), fail_silently=True)
                return destino
            messages.error(request, texto(_P + "msg_form_invalido"), fail_silently=True)

        elif acao == "remover_chave_ia":
            config.ia_chave = ""
            config.save()
            _auditar(request, "prospeccao:chave_ia_removida")
            messages.success(request, texto(_P + "msg_ia_removida"), fail_silently=True)
            return destino

        elif acao == "salvar_limiares":
            form_limiares = LimiaresForm(request.POST, instance=config)
            if form_limiares.is_valid():
                form_limiares.save()
                _auditar(request, "prospeccao:criterios_salvos")
                messages.success(request, texto(_P + "msg_limiares_salvos"), fail_silently=True)
                return destino
            messages.error(request, texto(_P + "msg_form_invalido"), fail_silently=True)

        elif acao == "recalcular":
            from apps.prospeccao.services import orquestrador

            total = 0
            for empresa in Empresa.objects.all().iterator():
                try:
                    orquestrador.recalcular_empresa(empresa, config)
                    total += 1
                except Exception:
                    logger.exception("Falha ao recalcular a empresa %s.", empresa.pk)
            _auditar(request, "prospeccao:metricas_recalculadas", objeto=str(total))
            messages.success(request, texto(_P + "msg_recalculado", total=total), fail_silently=True)
            return destino

        else:
            messages.error(request, texto(_P + "msg_acao_invalida"), fail_silently=True)
            return destino

    contexto = {
        "config": config,
        "form_chave": form_chave,
        "form_ia": form_ia,
        "form_limiares": form_limiares,
        "origem_chave": credenciais.origem_chave_google(),
        "metricas": _metricas_google(config),
        "buscas": Busca.objects.select_related("conexao").all()[:5],
    }
    return render(request, "prospeccao/painel.html", contexto)


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------
class EmpresaListView(AdminRequeridoMixin, ListView):
    """Lista paginada de empresas com filtros por status e problema."""

    model = Empresa
    template_name = "prospeccao/lista.html"
    context_object_name = "objetos_empresa"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Empresa]:
        self.config = ConfiguracaoProspeccao.obter()
        queryset = Empresa.objects.all()

        status = (self.request.GET.get("status") or "").strip()
        if status in Empresa.Status.values:
            queryset = queryset.filter(status_prospeccao=status)

        problema = (self.request.GET.get("problema") or "").strip()
        filtro = _filtro_por_slug(problema, self.config)
        if filtro is not None:
            queryset = queryset.filter(filtro)

        return queryset.order_by("-oportunidade_score", "-criado_em")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        pagina = contexto.get("page_obj")
        objetos = pagina.object_list if pagina is not None else contexto.get("object_list", [])

        # Linhas no formato EmpresaLinha (mesmo contrato da tabela do dashboard).
        contexto["linhas"] = [empresa.linha_dashboard(self.config) for empresa in objetos]
        contexto["filtro_status"] = self.request.GET.get("status", "")
        contexto["filtro_problema"] = self.request.GET.get("problema", "")
        contexto["opcoes_status"] = Empresa.Status.choices
        contexto["opcoes_problema"] = _opcoes_problema()
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


def _rotulo_situacao(status: str) -> str:
    return {
        STATUS_OPERACIONAL: texto(_D + "status_operacional"),
        STATUS_FECHADA_TEMPORARIAMENTE: texto(_D + "status_fechada_temporariamente"),
        STATUS_FECHADA_PERMANENTEMENTE: texto(_D + "status_fechada"),
    }.get(status or "", texto(_D + "status_desconhecido"))


def _rotulo_horario(situacao: str) -> str:
    return {
        HORARIO_OK: texto(_D + "horario_ok"),
        HORARIO_AUSENTE: texto(_D + "horario_ausente"),
        HORARIO_INCOMPLETO: texto(_D + "horario_incompleto"),
    }.get(situacao or "", texto("geral.sem_valor"))


class EmpresaDetailView(AdminRequeridoMixin, DetailView):
    """Ficha completa de uma empresa."""

    model = Empresa
    template_name = "prospeccao/detalhe.html"
    context_object_name = "empresa"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        empresa: Empresa = self.object
        config = ConfiguracaoProspeccao.obter()
        contexto["config"] = config
        contexto["linha"] = empresa.linha_dashboard(config)
        contexto["problemas"] = empresa.rotulos_problemas(config)
        contexto["problemas_badges"] = contexto["linha"]["problemas_badges"]
        contexto["situacao_google"] = _rotulo_situacao(empresa.status_google)
        contexto["horario_google"] = _rotulo_horario(empresa.situacao_horario)
        contexto["ia_disponivel"] = config.ia_disponivel
        return contexto


@admin_requerido
@csrf_protect
@require_POST
def atualizar_google(request: HttpRequest, pk: int) -> HttpResponse:
    """Consulta o Place Details da empresa e refaz a análise completa."""
    from apps.prospeccao.services import google_places, orquestrador

    empresa = get_object_or_404(Empresa.objects.select_related("busca__conexao"), pk=pk)
    conexao = empresa.busca.conexao if empresa.busca_id and empresa.busca else None
    try:
        orquestrador.atualizar_dados_google(empresa, conexao)
    except ValueError:
        messages.error(request, texto(_D + "msg_google_sem_place"), fail_silently=True)
    except google_places.ErroConfiguracao as exc:
        messages.error(request, texto(_D + "msg_google_erro", erro=str(exc)), fail_silently=True)
    except Exception:
        logger.exception("Falha ao atualizar os dados do Google da empresa %s.", empresa.pk)
        messages.error(
            request,
            texto(_D + "msg_google_erro", erro=texto("prospeccao.google.erro_rede")),
            fail_silently=True,
        )
    else:
        _auditar(request, "prospeccao:google_atualizado", objeto=empresa.nome)
        messages.success(request, texto(_D + "msg_google_ok"), fail_silently=True)
    return redirect("prospeccao:detalhe", pk=empresa.pk)


@admin_requerido
@csrf_protect
@require_POST
def diagnostico_ia(request: HttpRequest, pk: int) -> HttpResponse:
    """Gera (ou refaz) o diagnóstico em texto com a IA generativa (Claude)."""
    from apps.prospeccao.services import ia, orquestrador

    empresa = get_object_or_404(Empresa, pk=pk)
    config = ConfiguracaoProspeccao.obter()
    if not config.ia_ativa:
        messages.error(request, texto(_D + "ia_inativa"), fail_silently=True)
        return redirect("prospeccao:detalhe", pk=empresa.pk)
    try:
        conteudo = ia.gerar_diagnostico(
            orquestrador.dados_para_ia(empresa, config), config.ia_chave, config.ia_modelo
        )
    except ia.ErroIA as exc:
        messages.error(request, texto(_D + "msg_ia_erro", erro=str(exc)), fail_silently=True)
    except Exception:
        logger.exception("Falha inesperada ao gerar o diagnóstico com IA (empresa %s).", empresa.pk)
        messages.error(
            request,
            texto(_D + "msg_ia_erro", erro=texto("prospeccao.ia.erro_conexao")),
            fail_silently=True,
        )
    else:
        empresa.diagnostico_ia = conteudo
        empresa.diagnostico_ia_em = timezone.now()
        empresa.save(update_fields=["diagnostico_ia", "diagnostico_ia_em", "atualizado_em"])
        _auditar(request, "prospeccao:diagnostico_ia", objeto=empresa.nome)
        messages.success(request, texto(_D + "msg_ia_ok"), fail_silently=True)
    return redirect("prospeccao:detalhe", pk=empresa.pk)


# ---------------------------------------------------------------------------
# Conexões e buscas
# ---------------------------------------------------------------------------
@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def conexoes(request: HttpRequest) -> HttpResponse:
    """Lista e cria conexões do Google (a chave é salva cifrada)."""
    if request.method == "POST":
        form = ConexaoGoogleForm(request.POST)
        if form.is_valid():
            conexao = form.save(commit=False)
            conexao.criado_por = request.user
            conexao.save()
            _auditar(request, "prospeccao:conexao_criada", objeto=conexao.nome)
            messages.success(request, texto("prospeccao.conexoes.msg_criada"), fail_silently=True)
            return redirect("prospeccao:conexoes")
    else:
        form = ConexaoGoogleForm()

    contexto = {
        "form": form,
        "conexoes": ConexaoGoogle.objects.select_related("criado_por").all(),
    }
    return render(request, "prospeccao/conexoes.html", contexto)


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def nova_busca(request: HttpRequest) -> HttpResponse:
    """Cria uma nova busca (pendente). A execução é disparada à parte."""
    if request.method == "POST":
        form = BuscaForm(request.POST)
        if form.is_valid():
            busca = form.save(commit=False)
            busca.criado_por = request.user
            busca.status = Busca.Status.PENDENTE
            busca.save()
            _auditar(request, "prospeccao:busca_criada", objeto=str(busca))
            messages.success(request, texto("prospeccao.nova_busca.msg_criada"), fail_silently=True)
            return redirect("prospeccao:nova_busca")
    else:
        form = BuscaForm()

    contexto = {
        "form": form,
        "buscas": Busca.objects.select_related("conexao").all()[:20],
    }
    return render(request, "prospeccao/nova_busca.html", contexto)


@admin_requerido
@csrf_protect
@require_POST
def executar_busca(request: HttpRequest, pk: int) -> HttpResponse:
    """Dispara a execução (síncrona) de uma busca; estrutura pronta p/ Celery."""
    busca = get_object_or_404(Busca, pk=pk)
    _auditar(request, "prospeccao:busca_executada", objeto=str(busca))
    try:
        # Import tardio: a task carrega serviços potencialmente pesados.
        from apps.prospeccao.tasks import executar_busca as tarefa

        resultado = tarefa(busca.id)
        resultado = resultado if isinstance(resultado, dict) else {}
        if resultado.get("status") == "erro":
            messages.error(
                request,
                resultado.get("mensagem") or texto("prospeccao.nova_busca.msg_erro"),
                fail_silently=True,
            )
        else:
            messages.success(
                request,
                texto("prospeccao.nova_busca.msg_executada", total=int(resultado.get("total", 0))),
                fail_silently=True,
            )
    except Exception:
        logger.exception("Falha ao executar a busca %s.", busca.pk)
        messages.error(request, texto("prospeccao.nova_busca.msg_erro"), fail_silently=True)
    return redirect("prospeccao:nova_busca")

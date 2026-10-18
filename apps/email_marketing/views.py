"""Views do módulo de Marketing por E-mail (adendo 3 — MÓDULO 5).

Todas as views administrativas exigem ``is_staff`` (CBVs via
``AdminRequeridoMixin``; FBVs via ``@admin_requerido``) e as ações usam
``@csrf_protect`` + ``@require_POST``/``@require_http_methods`` e registram
auditoria. Defesa em profundidade: o ``SomenteAdminMiddleware`` já protege o site.

EXCEÇÃO: ``descadastrar`` é PÚBLICA (o destinatário de uma campanha não é
administrador). Ela é isenta do login pelo ``PUBLIC_URL_PREFIXES``; o POST
continua protegido por CSRF (middleware global). Ela só marca o descadastro,
nunca revela se um token existe além do necessário (token grande/aleatório) e
usa uma página STANDALONE.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView

from apps.contas.decorators import admin_requerido
from apps.contas.mixins import AdminRequeridoMixin
from apps.email_marketing.forms import (
    CampanhaForm,
    ConfiguracaoEnvioForm,
    ContatoImportacaoForm,
    ListaForm,
    TemplateEmailForm,
)
from apps.email_marketing.models import (
    Campanha,
    ConfiguracaoEnvio,
    Contato,
    EnvioEmail,
    Lista,
    TemplateEmail,
)

logger = logging.getLogger("modulos.email_marketing.views")

# Nº de contatos por página na listagem de contatos.
CONTATOS_POR_PAGINA = 25
# Nº de campanhas por página.
CAMPANHAS_POR_PAGINA = 20
# Amostra de envios exibida na ficha da campanha.
AMOSTRA_ENVIOS = 30


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


# ---------------------------------------------------------------------------
# Campanhas
# ---------------------------------------------------------------------------
class CampanhaListView(AdminRequeridoMixin, ListView):
    """Lista paginada de campanhas com status e contadores."""

    model = Campanha
    template_name = "email_marketing/campanhas.html"
    context_object_name = "campanhas"
    paginate_by = CAMPANHAS_POR_PAGINA

    def get_queryset(self) -> QuerySet[Campanha]:
        return Campanha.objects.select_related("configuracao", "lista").all()


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def campanha_nova(request: HttpRequest) -> HttpResponse:
    """Cria uma nova campanha (status RASCUNHO) e leva à ficha recém-criada."""
    if request.method == "POST":
        form = CampanhaForm(request.POST)
        if form.is_valid():
            campanha = form.save(commit=False)
            campanha.criado_por = request.user
            campanha.status = Campanha.Status.RASCUNHO
            campanha.save()
            _auditar(request, "email_marketing:campanha_criada", objeto=str(campanha))
            messages.success(request, _("Campanha criada como rascunho."), fail_silently=True)
            return redirect("email_marketing:campanha_detalhe", pk=campanha.pk)
    else:
        # Pré-preenche a partir de um modelo (template) da biblioteca, se pedido.
        inicial: dict = {}
        template_id = request.GET.get("template")
        if template_id:
            modelo = TemplateEmail.objects.filter(pk=template_id, ativo=True).first()
            if modelo is not None:
                inicial = {
                    "corpo_html": modelo.corpo_html,
                    "corpo_texto": modelo.corpo_texto,
                    "nome": modelo.nome,
                }
                messages.info(
                    request,
                    _("Modelo “%(nome)s” aplicado. Edite o conteúdo à vontade.")
                    % {"nome": modelo.nome},
                    fail_silently=True,
                )
        form = CampanhaForm(initial=inicial)

    contexto = {
        "form": form,
        "modo": "nova",
        "templates": TemplateEmail.objects.filter(ativo=True),
    }
    return render(request, "email_marketing/campanha_form.html", contexto)


# ---------------------------------------------------------------------------
# Biblioteca de modelos (templates) de e-mail
# ---------------------------------------------------------------------------
@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def templates_lista(request: HttpRequest) -> HttpResponse:
    """Lista os modelos de e-mail e cria um novo."""
    if request.method == "POST":
        form = TemplateEmailForm(request.POST)
        if form.is_valid():
            modelo = form.save()
            _auditar(request, "email_marketing:template_criado", objeto=str(modelo))
            messages.success(request, _("Modelo de e-mail criado."), fail_silently=True)
            return redirect("email_marketing:templates")
    else:
        form = TemplateEmailForm()

    contexto = {
        "form": form,
        "templates": TemplateEmail.objects.all(),
    }
    return render(request, "email_marketing/templates.html", contexto)


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def template_editar(request: HttpRequest, pk: int) -> HttpResponse:
    """Edita um modelo de e-mail existente (100% editável)."""
    modelo = get_object_or_404(TemplateEmail, pk=pk)
    if request.method == "POST":
        form = TemplateEmailForm(request.POST, instance=modelo)
        if form.is_valid():
            form.save()
            _auditar(request, "email_marketing:template_editado", objeto=str(modelo))
            messages.success(request, _("Modelo atualizado."), fail_silently=True)
            return redirect("email_marketing:templates")
    else:
        form = TemplateEmailForm(instance=modelo)
    return render(
        request,
        "email_marketing/template_form.html",
        {"form": form, "modelo": modelo},
    )


@admin_requerido
@csrf_protect
@require_POST
def template_excluir(request: HttpRequest, pk: int) -> HttpResponse:
    """Exclui um modelo de e-mail."""
    modelo = get_object_or_404(TemplateEmail, pk=pk)
    nome = str(modelo)
    modelo.delete()
    _auditar(request, "email_marketing:template_excluido", objeto=nome)
    messages.success(request, _("Modelo excluído."), fail_silently=True)
    return redirect("email_marketing:templates")


class CampanhaDetailView(AdminRequeridoMixin, DetailView):
    """Ficha da campanha: contadores, nº de destinatários atuais e amostra de envios."""

    model = Campanha
    template_name = "email_marketing/campanha_detalhe.html"
    context_object_name = "campanha"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        campanha: Campanha = self.object

        total = campanha.total_destinatarios

        def pct(parte: int) -> int:
            return round(parte / total * 100) if total else 0

        contexto["num_destinatarios"] = campanha.destinatarios().count()
        contexto["pode_enviar"] = campanha.pode_enviar()
        contexto["envios"] = list(
            campanha.envios.select_related("contato")[:AMOSTRA_ENVIOS]
        )
        contexto["pct_enviados"] = pct(campanha.total_enviados)
        contexto["pct_falhas"] = pct(campanha.total_falhas)
        return contexto


@admin_requerido
@csrf_protect
@require_POST
def campanha_enviar(request: HttpRequest, pk: int) -> HttpResponse:
    """Envia a campanha SINCRONAMENTE (estrutura pronta para migrar a Celery)."""
    campanha = get_object_or_404(Campanha, pk=pk)

    if not campanha.pode_enviar():
        messages.warning(
            request,
            _("Esta campanha não pode ser enviada no estado atual."),
            fail_silently=True,
        )
        return redirect("email_marketing:campanha_detalhe", pk=campanha.pk)

    _auditar(request, "email_marketing:campanha_enviada", objeto=str(campanha))
    try:
        from apps.email_marketing.services import enviador

        resultado = enviador.enviar_campanha(campanha)
    except Exception:
        logger.exception("Falha inesperada ao enviar a campanha %s.", campanha.pk)
        messages.error(
            request,
            _("Não foi possível enviar a campanha. Tente novamente."),
            fail_silently=True,
        )
        return redirect("email_marketing:campanha_detalhe", pk=campanha.pk)

    enviados = resultado.get("enviados", 0)
    falhas = resultado.get("falhas", 0)
    total = resultado.get("total", 0)
    if total == 0:
        messages.warning(
            request,
            _("A campanha não tem destinatários inscritos. Adicione contatos e tente novamente."),
            fail_silently=True,
        )
    elif enviados == 0:
        # Nenhum e-mail saiu: falha geral (conexão/credenciais) ou todas falharam.
        messages.error(
            request,
            _("Não foi possível enviar a campanha: nenhum e-mail foi enviado. "
              "Verifique a configuração de envio (SMTP)."),
            fail_silently=True,
        )
    elif falhas == 0:
        messages.success(
            request,
            _("Campanha enviada: %(enviados)d e-mail(s) enviado(s).") % {"enviados": enviados},
            fail_silently=True,
        )
    else:
        messages.warning(
            request,
            _("Campanha enviada parcialmente: %(enviados)d enviado(s), %(falhas)d falha(s).")
            % {"enviados": enviados, "falhas": falhas},
            fail_silently=True,
        )
    return redirect("email_marketing:campanha_detalhe", pk=campanha.pk)


# ---------------------------------------------------------------------------
# Configurações de envio
# ---------------------------------------------------------------------------
@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def configuracoes(request: HttpRequest) -> HttpResponse:
    """Lista as configurações de envio (sem segredos) e cria uma nova."""
    if request.method == "POST":
        form = ConfiguracaoEnvioForm(request.POST)
        if form.is_valid():
            configuracao = form.save(commit=False)
            configuracao.criado_por = request.user
            configuracao.save()
            _auditar(request, "email_marketing:config_criada", objeto=str(configuracao))
            messages.success(request, _("Configuração de envio criada."), fail_silently=True)
            return redirect("email_marketing:configuracoes")
    else:
        form = ConfiguracaoEnvioForm()

    contexto = {
        "form": form,
        "configuracoes": ConfiguracaoEnvio.objects.all(),
    }
    return render(request, "email_marketing/configuracoes.html", contexto)


@admin_requerido
@csrf_protect
@require_POST
def config_testar(request: HttpRequest, pk: int) -> HttpResponse:
    """Envia um e-mail de teste por uma configuração (valida o e-mail de destino)."""
    configuracao = get_object_or_404(ConfiguracaoEnvio, pk=pk)

    destinatario = (request.POST.get("destinatario") or "").strip()
    try:
        validate_email(destinatario)
    except ValidationError:
        messages.error(request, _("Informe um e-mail de destino válido."), fail_silently=True)
        return redirect("email_marketing:configuracoes")

    from apps.email_marketing.services import enviador

    ok, mensagem = enviador.enviar_teste(configuracao, destinatario)
    _auditar(
        request,
        "email_marketing:config_teste",
        objeto=f"{configuracao} -> {destinatario} [{'ok' if ok else 'falha'}]",
    )
    if ok:
        messages.success(request, mensagem, fail_silently=True)
    else:
        messages.warning(request, mensagem, fail_silently=True)
    return redirect("email_marketing:configuracoes")


# ---------------------------------------------------------------------------
# Contatos
# ---------------------------------------------------------------------------
@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def contatos(request: HttpRequest) -> HttpResponse:
    """Lista os contatos (paginado) e importa novos em massa (um por linha)."""
    if request.method == "POST":
        form = ContatoImportacaoForm(request.POST)
        if form.is_valid():
            criados, existentes = _importar_contatos(form.entradas_validas)
            invalidas = len(getattr(form, "linhas_invalidas", []))
            _auditar(
                request,
                "email_marketing:contatos_importados",
                objeto=f"{criados} novo(s), {existentes} existente(s), {invalidas} inválida(s)",
            )
            messages.success(
                request,
                _("Importação concluída: %(criados)d novo(s), %(existentes)d já existente(s).")
                % {"criados": criados, "existentes": existentes},
                fail_silently=True,
            )
            if invalidas:
                messages.warning(
                    request,
                    _("%(invalidas)d linha(s) ignorada(s) por e-mail inválido.")
                    % {"invalidas": invalidas},
                    fail_silently=True,
                )
            return redirect("email_marketing:contatos")
    else:
        form = ContatoImportacaoForm()

    from django.core.paginator import Paginator

    paginator = Paginator(Contato.objects.all(), CONTATOS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("page"))

    contexto = {
        "form": form,
        "contatos": pagina.object_list,
        "page_obj": pagina,
        "is_paginated": pagina.has_other_pages(),
        "total_contatos": paginator.count,
    }
    return render(request, "email_marketing/contatos.html", contexto)


def _importar_contatos(entradas: list[tuple[str, str]]) -> tuple[int, int]:
    """Cria contatos por ``get_or_create`` (idempotente). Retorna (criados, existentes)."""
    criados = 0
    existentes = 0
    for nome, email in entradas:
        _obj, foi_criado = Contato.objects.get_or_create(
            email=email,
            defaults={"nome": nome, "origem": "importação"},
        )
        if foi_criado:
            criados += 1
        else:
            existentes += 1
    return criados, existentes


# ---------------------------------------------------------------------------
# Listas
# ---------------------------------------------------------------------------
@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def listas(request: HttpRequest) -> HttpResponse:
    """Lista as listas de contatos e cria uma nova (multisseleção de contatos)."""
    if request.method == "POST":
        form = ListaForm(request.POST)
        if form.is_valid():
            lista = form.save()
            _auditar(request, "email_marketing:lista_criada", objeto=str(lista))
            messages.success(request, _("Lista criada com sucesso."), fail_silently=True)
            return redirect("email_marketing:listas")
    else:
        form = ListaForm()

    contexto = {
        "form": form,
        "listas": Lista.objects.prefetch_related("contatos").all(),
    }
    return render(request, "email_marketing/listas.html", contexto)


# ---------------------------------------------------------------------------
# Descadastro (PÚBLICO)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(["GET", "POST"])
def descadastrar(request: HttpRequest, token: str) -> HttpResponse:
    """Página pública de descadastro tokenizada (GET confirma, POST efetiva).

    - Sem login (isenta pelo ``PUBLIC_URL_PREFIXES``).
    - ``csrf_exempt``: além do formulário humano, aceita o POST de "one-click"
      dos provedores (RFC 8058 — cabeçalho ``List-Unsubscribe-Post``), que não
      envia token CSRF. A segurança vem do TOKEN grande e aleatório da URL
      (inguessável) e a ação é idempotente e de baixo impacto (apenas opt-out).
    - Token não encontrado -> página "link inválido" (sem enumeração).
    - Só marca o descadastro; nenhuma outra ação. Página STANDALONE.
    """
    contato = Contato.objects.filter(token_descadastro=token).first()
    if contato is None:
        return render(
            request,
            "email_marketing/descadastrar.html",
            {"estado": "invalido"},
            status=404,
        )

    if request.method == "POST":
        contato.descadastrar()
        _auditar(request, "email_marketing:descadastro", objeto=contato.email)
        return render(
            request,
            "email_marketing/descadastrar.html",
            {"estado": "sucesso", "contato": contato},
        )

    estado = "confirmar" if contato.inscrito else "ja_descadastrado"
    return render(
        request,
        "email_marketing/descadastrar.html",
        {"estado": estado, "contato": contato},
    )

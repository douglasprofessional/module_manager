"""Views do núcleo.

- ``dashboard``: consolida os defaults do painel com os dados dos módulos
  HABILITADOS (respeita o liga/desliga de módulos).
- ``configuracoes``: painel de "Configurações Gerais do Sistema" (marca branca,
  liga/desliga de módulos e exclusão de dados por módulo).
- ``alternar_tema`` / ``alternar_modulo`` / ``excluir_dados_modulo``: ações
  (POST) do painel de configurações e da barra superior.

Acesso restrito: todas exigem autenticado + ``is_staff`` (além da proteção
global do ``SomenteAdminMiddleware``).
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.contas.decorators import admin_requerido

from .forms import ConfiguracaoSistemaForm
from .models import ConfiguracaoSistema, ModuloEstado, Tema
from .modulos import registro

logger = logging.getLogger("modulos.nucleo.views")


def _painel_padrao() -> dict:
    """Retorna o ``painel`` com defaults zerados de TODAS as chaves (seção 7)."""
    return {
        # Card 1 — "Resumo de Prospecção" (gráfico de linha).
        "total_empresas": 0,
        "novas_semana": 0,
        "variacao_pct": 0.0,
        "serie_encontradas": [],
        "serie_qualificadas": [],
        # Card 2 — "Oportunidades" (donut + legenda).
        "oportunidades_total": 0,
        "oportunidades": [],
        # Card 3 — "Próximas ações".
        "proximas_acoes": [],
        # Card 4 — "Empresas encontradas" (tabela principal).
        "empresas": [],
        # Card 5 — "Meta de prospecção".
        "meta_atual": 0,
        "meta_total": 0,
        "meta_pct": 0,
        # Card 6 — "Destaques".
        "destaque_titulo": "",
        "destaque_texto": "",
    }


def _auditar(request: HttpRequest, acao: str, objeto: str = "") -> None:
    """Registra uma ação administrativa na trilha de auditoria (resiliente)."""
    try:
        from .models import RegistroAuditoria

        RegistroAuditoria.objects.create(
            usuario=request.user if request.user.is_authenticated else None,
            acao=acao,
            objeto_repr=(objeto or "")[:255],
            ip=(request.META.get("REMOTE_ADDR") or None),
        )
    except Exception:
        logger.exception("Falha ao auditar ação '%s'.", acao)


@admin_requerido
def dashboard(request: HttpRequest) -> HttpResponse:
    """Renderiza o dashboard consolidando defaults + dados dos módulos habilitados."""
    painel = _painel_padrao()
    slugs = ModuloEstado.slugs_habilitados()

    try:
        contribuicoes = registro.contexto_dashboard(request, slugs)
        if isinstance(contribuicoes, dict):
            painel.update(contribuicoes)
    except Exception:  # pragma: no cover - o dashboard nunca deve quebrar por um módulo
        logger.exception("Falha ao mesclar contexto_dashboard dos módulos; usando defaults.")

    try:
        cards_modulos = registro.cards_resumo(request, slugs)
    except Exception:  # pragma: no cover
        logger.exception("Falha ao coletar cards_resumo dos módulos.")
        cards_modulos = []

    return render(
        request,
        "nucleo/dashboard.html",
        {
            "painel": painel,
            "cards_modulos": cards_modulos,
            "modulos_ativos": slugs,
            "algum_modulo_ativo": bool(slugs),
        },
    )


def _modulos_para_configuracao() -> list[dict]:
    """Lista todos os módulos registrados com estado (on/off) e suporte a exclusão."""
    habilitados = ModuloEstado.slugs_habilitados()
    linhas: list[dict] = []
    for modulo in registro.todos():
        slug = getattr(modulo, "slug", "")
        if not slug:
            continue
        linhas.append(
            {
                "slug": slug,
                "nome": getattr(modulo, "nome", "") or slug,
                "descricao": getattr(modulo, "descricao", ""),
                "icone": getattr(modulo, "icone", "dashboard"),
                "habilitado": slug in habilitados,
                "suporta_exclusao": modulo.suporta_exclusao(),
            }
        )
    return linhas


@admin_requerido
def configuracoes(request: HttpRequest) -> HttpResponse:
    """Painel de Configurações Gerais do Sistema (marca branca + módulos)."""
    config = ConfiguracaoSistema.obter()

    if request.method == "POST":
        form = ConfiguracaoSistemaForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            _auditar(request, "config:salvar", objeto=form.cleaned_data.get("nome_sistema", ""))
            messages.success(request, "Configurações salvas com sucesso.")
            return redirect(reverse("nucleo:configuracoes"))
        messages.error(request, "Verifique os campos destacados.")
    else:
        form = ConfiguracaoSistemaForm(instance=config)

    return render(
        request,
        "nucleo/configuracoes.html",
        {
            "form": form,
            "config": config,
            "modulos": _modulos_para_configuracao(),
            "temas": Tema.choices,
        },
    )


@admin_requerido
@require_POST
def alternar_tema(request: HttpRequest) -> HttpResponse:
    """Alterna o tema do usuário logado (claro <-> escuro) e persiste."""
    usuario = request.user
    novo = Tema.ESCURO if getattr(usuario, "tema", Tema.CLARO) == Tema.CLARO else Tema.CLARO
    try:
        usuario.tema = novo
        usuario.save(update_fields=["tema"])
    except Exception:
        logger.exception("Falha ao alternar tema do usuário.")
    destino = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    # Anti open redirect: só volta para URLs da própria origem.
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        destino = reverse("nucleo:dashboard")
    return redirect(destino)


@admin_requerido
@require_POST
def alternar_modulo(request: HttpRequest) -> HttpResponse:
    """Liga/desliga um módulo pelo ``slug``. Desligar NÃO apaga dados."""
    slug = (request.POST.get("slug") or "").strip()
    modulo = registro.obter(slug)
    if modulo is None:
        messages.error(request, "Módulo desconhecido.")
        return redirect(reverse("nucleo:configuracoes"))

    habilitar = (request.POST.get("habilitar") or "").strip() in {"1", "true", "on", "sim"}
    ModuloEstado.definir(slug, habilitar)
    _auditar(request, "modulo:on" if habilitar else "modulo:off", objeto=slug)
    messages.success(
        request,
        f"Módulo “{getattr(modulo, 'nome', slug)}” {'habilitado' if habilitar else 'desabilitado'}.",
    )
    return redirect(reverse("nucleo:configuracoes"))


@admin_requerido
@require_POST
def excluir_dados_modulo(request: HttpRequest) -> HttpResponse:
    """Exclui TODOS os dados de um módulo (ação destrutiva, com confirmação).

    Requer o texto de confirmação "EXCLUIR" para evitar exclusões acidentais.
    """
    slug = (request.POST.get("slug") or "").strip()
    modulo = registro.obter(slug)
    if modulo is None:
        messages.error(request, "Módulo desconhecido.")
        return redirect(reverse("nucleo:configuracoes"))

    confirmacao = (request.POST.get("confirmacao") or "").strip().upper()
    if confirmacao != "EXCLUIR":
        messages.error(request, "Digite EXCLUIR para confirmar a exclusão dos dados.")
        return redirect(reverse("nucleo:configuracoes"))

    try:
        removidos = int(modulo.excluir_dados(request) or 0)
    except Exception:
        logger.exception("Falha ao excluir dados do módulo '%s'.", slug)
        messages.error(request, "Não foi possível excluir os dados deste módulo.")
        return redirect(reverse("nucleo:configuracoes"))

    _auditar(request, "modulo:excluir_dados", objeto=f"{slug}:{removidos}")
    messages.success(
        request,
        f"Dados do módulo “{getattr(modulo, 'nome', slug)}” excluídos "
        f"({removidos} registro(s) removido(s)).",
    )
    return redirect(reverse("nucleo:configuracoes"))

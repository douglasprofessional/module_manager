"""Views de autenticação: login com throttling por (ip+email), logout e auditoria."""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.contas.decorators import admin_requerido
from apps.contas.forms import AlterarSenhaForm, LoginForm, PerfilForm
from apps.contas.middleware import InatividadeSessaoMiddleware
from apps.contas.models import Usuario

logger = logging.getLogger(__name__)

# --- Auditoria (ações registradas) ------------------------------------------
ACAO_LOGIN = "login"
ACAO_LOGOUT = "logout"
ACAO_TENTATIVA = "tentativa"

# --- Throttling de login ----------------------------------------------------
LIMITE_TENTATIVAS = 5
JANELA_BLOQUEIO_SEGUNDOS = 15 * 60  # 15 minutos
PREFIXO_CACHE = "contas:login:tentativas:"

TEMPLATE_LOGIN = "contas/login.html"


# --- Helpers ----------------------------------------------------------------
def _obter_ip(request: HttpRequest) -> str:
    """IP do cliente. Usa REMOTE_ADDR (não confiar em cabeçalhos de proxy)."""
    return request.META.get("REMOTE_ADDR", "") or ""


def _chave_throttle(ip: str, email: str) -> str:
    """Chave de cache por (ip + email), normalizada e com hash (segura p/ backend)."""
    base = f"{ip}|{(email or '').strip().lower()}"
    return PREFIXO_CACHE + hashlib.sha256(base.encode("utf-8")).hexdigest()


def _tentativas(chave: str) -> int:
    try:
        return int(cache.get(chave, 0))
    except Exception:  # backend de cache indisponível não deve quebrar o login
        logger.exception("Falha ao ler contador de tentativas de login.")
        return 0


def _bloqueado(chave: str) -> bool:
    return _tentativas(chave) >= LIMITE_TENTATIVAS


def _registrar_falha(chave: str) -> int:
    """Incrementa o contador de falhas e mantém a janela de bloqueio."""
    try:
        atual = _tentativas(chave) + 1
        cache.set(chave, atual, JANELA_BLOQUEIO_SEGUNDOS)
        return atual
    except Exception:
        logger.exception("Falha ao registrar tentativa de login.")
        return 0


def _limpar_tentativas(chave: str) -> None:
    try:
        cache.delete(chave)
    except Exception:
        logger.exception("Falha ao limpar tentativas de login.")


def _registrar_auditoria(
    request: HttpRequest,
    acao: str,
    objeto: str = "",
    usuario: Any = None,
) -> None:
    """Registra um evento de auditoria.

    Importa ``RegistroAuditoria`` de ``apps.nucleo.models`` dentro da função
    para evitar import circular. Nunca deixa a auditoria quebrar o fluxo de auth.
    """
    try:
        from apps.nucleo.models import RegistroAuditoria

        RegistroAuditoria.objects.create(
            usuario=usuario,
            acao=acao,
            # Trunca para o max_length do campo: um e-mail gigante no POST não
            # pode causar DataError e suprimir a auditoria da tentativa.
            objeto_repr=(objeto or "")[:255],
            ip=(_obter_ip(request) or None),
        )
    except Exception:
        logger.exception("Falha ao registrar auditoria (acao=%s).", acao)


def _atualizar_ultimo_ip(usuario: Usuario, ip: str) -> None:
    """Persiste o último IP do usuário sem disparar signals (update direto)."""
    if not ip:
        return
    try:
        Usuario.objects.filter(pk=usuario.pk).update(ultimo_ip=ip)
    except Exception:
        logger.exception("Falha ao atualizar último IP do usuário.")


def _destino_seguro(proximo: str, request: HttpRequest) -> str:
    """Valida o parâmetro 'next': só redireciona para URL interna segura."""
    if proximo and url_has_allowed_host_and_scheme(
        url=proximo,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        # Nunca volta para login/logout (evita laço de redirecionamento).
        caminho = urlsplit(proximo).path
        if caminho not in {resolve_url(settings.LOGIN_URL), reverse("contas:logout")}:
            return proximo
    return resolve_url(settings.LOGIN_REDIRECT_URL)


# --- Views ------------------------------------------------------------------
@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    """Tela de login com throttling por (ip+email) e auditoria de tentativas."""
    proximo = request.POST.get("next") or request.GET.get("next", "") or ""

    if request.user.is_authenticated:
        return redirect(_destino_seguro(proximo, request))

    contexto: dict[str, Any] = {"proximo": proximo}

    if request.method == "POST":
        email_informado = request.POST.get("email", "")
        ip = _obter_ip(request)
        chave = _chave_throttle(ip, email_informado)

        if _bloqueado(chave):
            _registrar_auditoria(request, ACAO_TENTATIVA, objeto=email_informado)
            messages.error(
                request,
                _(
                    "Muitas tentativas de login. Tente novamente em alguns minutos."
                ),
                fail_silently=True,
            )
            contexto["form"] = LoginForm(request=request)
            return render(request, TEMPLATE_LOGIN, contexto, status=429)

        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            usuario = form.get_usuario()
            _limpar_tentativas(chave)
            auth_login(request, usuario)  # cicla a sessão (anti session fixation)
            request.session[InatividadeSessaoMiddleware.CHAVE_SESSAO] = int(time.time())
            _atualizar_ultimo_ip(usuario, ip)
            _registrar_auditoria(
                request, ACAO_LOGIN, objeto=usuario.email, usuario=usuario
            )
            return redirect(_destino_seguro(proximo, request))

        # Falha: conta a tentativa e audita (sem revelar o motivo).
        total = _registrar_falha(chave)
        _registrar_auditoria(request, ACAO_TENTATIVA, objeto=email_informado)
        if total >= LIMITE_TENTATIVAS:
            messages.error(
                request,
                _(
                    "Muitas tentativas de login. Tente novamente em alguns minutos."
                ),
                fail_silently=True,
            )
        contexto["form"] = form
        return render(request, TEMPLATE_LOGIN, contexto)

    contexto["form"] = LoginForm(request=request)
    return render(request, TEMPLATE_LOGIN, contexto)


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    """Encerra a sessão (somente via POST com CSRF) e registra a auditoria.

    Um GET nunca desloga (evita logout acidental por prefetch do navegador ou
    links forjados): apenas redireciona para o dashboard ou para o login.
    """
    if request.method != "POST":
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return redirect(settings.LOGOUT_REDIRECT_URL)
    usuario = request.user if request.user.is_authenticated else None
    if usuario is not None:
        _registrar_auditoria(
            request, ACAO_LOGOUT, objeto=usuario.email, usuario=usuario
        )
    auth_logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


@never_cache
@admin_requerido
@require_http_methods(["GET", "POST"])
def perfil_view(request: HttpRequest) -> HttpResponse:
    """Perfil do usuário: edita nome/e-mail/foto/tema e troca de senha.

    Dois formulários na mesma página, distinguidos pelo campo oculto ``acao``.
    """
    from django.contrib.auth import update_session_auth_hash

    perfil_form = PerfilForm(instance=request.user)
    senha_form = AlterarSenhaForm(request.user)

    if request.method == "POST":
        acao = request.POST.get("acao", "")
        if acao == "perfil":
            perfil_form = PerfilForm(
                request.POST, request.FILES, instance=request.user
            )
            if perfil_form.is_valid():
                perfil_form.save()
                _registrar_auditoria(
                    request, "perfil:atualizar", objeto=request.user.email,
                    usuario=request.user,
                )
                messages.success(request, _("Perfil atualizado com sucesso."))
                return redirect("contas:perfil")
            messages.error(request, _("Verifique os campos destacados."))
        elif acao == "senha":
            senha_form = AlterarSenhaForm(request.user, request.POST)
            if senha_form.is_valid():
                request.user.set_password(senha_form.cleaned_data["nova_senha"])
                request.user.save(update_fields=["password"])
                update_session_auth_hash(request, request.user)  # mantém logado
                _registrar_auditoria(
                    request, "perfil:senha", objeto=request.user.email,
                    usuario=request.user,
                )
                messages.success(request, _("Senha alterada com sucesso."))
                return redirect("contas:perfil")
            messages.error(request, _("Não foi possível alterar a senha."))

    return render(
        request,
        "contas/perfil.html",
        {"perfil_form": perfil_form, "senha_form": senha_form},
    )

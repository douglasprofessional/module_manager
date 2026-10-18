"""Middleware que restringe todo o sistema a administradores autenticados.

Libera apenas: login, logout, o admin do Django e os arquivos estáticos/mídia.
Para as demais rotas exige ``is_authenticated`` e ``is_staff``; caso contrário
redireciona para ``contas:login`` preservando o ``?next=``.

IMPORTANTE: deve ser posicionado APÓS ``AuthenticationMiddleware`` no MIDDLEWARE.
"""
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import resolve_url
from django.urls import reverse


class SomenteAdminMiddleware:
    """Bloqueia o acesso de não administradores fora das rotas liberadas."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        # Calculados de forma preguiçosa (na 1ª request, com o URLconf já carregado).
        self._urls_livres: set[str] | None = None
        self._prefixos_livres: tuple[str, ...] | None = None

    @staticmethod
    def _somente_caminho(url: str) -> str:
        """Extrai apenas o caminho de STATIC_URL/MEDIA_URL (podem ser absolutos)."""
        return urlsplit(url).path or url

    def _garantir_isencoes(self) -> None:
        if self._urls_livres is not None:
            return

        urls_livres: set[str] = set()
        for nome in ("contas:login", "contas:logout"):
            try:
                urls_livres.add(reverse(nome))
            except Exception:
                # URLconf ainda não pronto: tenta de novo na próxima request.
                self._urls_livres = None
                self._prefixos_livres = None
                return

        prefixos: list[str] = []
        try:
            # Reflete o prefixo real do admin (mesmo alterado via DJANGO_ADMIN_URL).
            prefixos.append(reverse("admin:index"))
        except Exception:
            pass

        for url_estatica in (
            getattr(settings, "STATIC_URL", "") or "",
            getattr(settings, "MEDIA_URL", "") or "",
        ):
            caminho = self._somente_caminho(url_estatica)
            if caminho:
                prefixos.append(caminho)

        # Prefixos públicos declarados por módulos (ex.: descadastro de e-mail).
        # O destinatário de uma campanha não é admin — estas rotas são isentas.
        for prefixo in getattr(settings, "PUBLIC_URL_PREFIXES", ()) or ():
            prefixo = (prefixo or "").strip()
            if prefixo:
                prefixos.append(prefixo)

        self._urls_livres = urls_livres
        self._prefixos_livres = tuple(p for p in prefixos if p)

    def _liberado(self, request: HttpRequest) -> bool:
        caminho = request.path
        if self._urls_livres and caminho in self._urls_livres:
            return True
        if self._prefixos_livres and caminho.startswith(self._prefixos_livres):
            return True
        return False

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._garantir_isencoes()

        if self._liberado(request):
            return self.get_response(request)

        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and usuario.is_staff:
            return self.get_response(request)

        return redirect_to_login(
            request.get_full_path(),
            resolve_url(settings.LOGIN_URL),
            "next",
        )


class InatividadeSessaoMiddleware:
    """Encerra a sessão do usuário após um período sem navegação.

    A cada navegação de página (requisições que não são chamadas assíncronas
    em segundo plano) grava o carimbo de última atividade na sessão. Se o
    intervalo desde a última atividade exceder ``SESSAO_INATIVIDADE_SEGUNDOS``
    (padrão: 600s = 10 minutos), faz o logout e redireciona para o login.

    IMPORTANTE: deve ficar APÓS ``AuthenticationMiddleware`` e
    ``MessageMiddleware`` e ANTES do ``SomenteAdminMiddleware``.
    """

    CHAVE_SESSAO = "_ultima_atividade"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    @staticmethod
    def _limite() -> int:
        try:
            return max(60, int(getattr(settings, "SESSAO_INATIVIDADE_SEGUNDOS", 600)))
        except (TypeError, ValueError):
            return 600

    @staticmethod
    def _requisicao_em_segundo_plano(request: HttpRequest) -> bool:
        """Chamadas assíncronas (fetch/XHR) não contam como navegação."""
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        return request.headers.get("Sec-Fetch-Dest", "") == "empty"

    def __call__(self, request: HttpRequest) -> HttpResponse:
        import time

        from django.contrib import messages
        from django.contrib.auth import logout

        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            return self.get_response(request)

        agora = int(time.time())
        ultima = request.session.get(self.CHAVE_SESSAO)

        try:
            ultima = int(ultima) if ultima is not None else None
        except (TypeError, ValueError):
            ultima = None

        if ultima is not None and agora - ultima > self._limite():
            logout(request)
            messages.warning(
                request,
                "Sua sessão foi encerrada por inatividade. Entre novamente.",
                fail_silently=True,
            )
            if self._requisicao_em_segundo_plano(request):
                from django.http import JsonResponse

                return JsonResponse(
                    {"erro": "sessao_expirada", "login": resolve_url(settings.LOGIN_URL)},
                    status=401,
                )
            url_login = resolve_url(settings.LOGIN_URL)
            if request.path in {url_login, reverse("contas:logout")}:
                from django.shortcuts import redirect

                return redirect(url_login)
            return redirect_to_login(
                request.get_full_path(),
                resolve_url(settings.LOGIN_URL),
                "next",
            )

        if ultima is None or not self._requisicao_em_segundo_plano(request):
            request.session[self.CHAVE_SESSAO] = agora

        return self.get_response(request)

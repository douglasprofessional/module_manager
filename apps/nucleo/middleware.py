"""Middleware de cabeçalhos de segurança (seção 9 da SPEC).

Adiciona a todas as respostas uma CSP simples (sem CDN externa), além de
``X-Content-Type-Options``, ``Referrer-Policy`` e ``Permissions-Policy``.

Usa ``setdefault`` para não sobrescrever cabeçalhos já definidos por outros
middlewares (ex.: SecurityMiddleware) ou pelas próprias views.
"""
from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

# CSP alinhada à seção 9: tudo servido localmente, EXCETO as fontes do Google
# Fonts (Staatliches + Inter), explicitamente liberadas nos hosts oficiais:
#   - CSS das fontes:   https://fonts.googleapis.com  (style-src)
#   - Arquivos .woff2:  https://fonts.gstatic.com     (font-src)
# Nenhum outro host externo é permitido (nada de scripts/CDN de terceiros).
POLITICA_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

# Uploads (logo, fotos, imagens) nunca executam scripts: protege contra SVG
# malicioso enviado como logo/foto (XSS armazenado na mesma origem).
POLITICA_CSP_MIDIA = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"

# Desliga recursos sensíveis do navegador que o app não usa.
POLITICA_PERMISSOES = "geolocation=(), microphone=(), camera=(), payment=()"


class CabecalhosSegurancaMiddleware:
    """Aplica cabeçalhos de segurança em cada resposta."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        prefixo_midia = "/" + (getattr(settings, "MEDIA_URL", "") or "media/").lstrip("/")
        if request.path.startswith(prefixo_midia):
            response["Content-Security-Policy"] = POLITICA_CSP_MIDIA
        response.setdefault("Content-Security-Policy", POLITICA_CSP)
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", POLITICA_PERMISSOES)
        return response

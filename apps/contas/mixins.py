"""Mixin de acesso restrito a administradores para views baseadas em classe."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import resolve_url


class AdminRequeridoMixin:
    """Exige usuário autenticado e ``is_staff``; senão redireciona ao login com ?next=.

    Aplica a mesma regra do ``admin_requerido`` (FBV) e do ``SomenteAdminMiddleware``.
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        usuario = getattr(request, "user", None)
        if not (usuario is not None and usuario.is_authenticated and usuario.is_staff):
            return redirect_to_login(
                request.get_full_path(),
                resolve_url(settings.LOGIN_URL),
                "next",
            )
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

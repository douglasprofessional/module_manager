"""Decorador de acesso restrito a administradores para views baseadas em função."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import resolve_url


def admin_requerido(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Exige usuário autenticado e ``is_staff``; senão redireciona ao login com ?next=."""

    @wraps(view_func)
    def _protegida(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and usuario.is_staff:
            return view_func(request, *args, **kwargs)
        return redirect_to_login(
            request.get_full_path(),
            resolve_url(settings.LOGIN_URL),
            "next",
        )

    return _protegida

"""Roteamento raiz do modulos.

Inclui os apps por namespace (seção 3 da SPEC), monta o admin sob um prefixo
configurável por ambiente e define os handlers de erro (templates em 'erros/').
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path


def _prefixo_admin() -> str:
    """Normaliza o prefixo do admin: sem barra inicial, com barra final."""
    bruto = (getattr(settings, "DJANGO_ADMIN_URL", "admin/") or "admin/").strip()
    bruto = bruto.lstrip("/")
    if not bruto.endswith("/"):
        bruto = f"{bruto}/"
    return bruto


urlpatterns = [
    path(_prefixo_admin(), admin.site.urls),
    path("contas/", include(("apps.contas.urls", "contas"), namespace="contas")),
    path(
        "prospeccao/",
        include(("apps.prospeccao.urls", "prospeccao"), namespace="prospeccao"),
    ),
    path("kanban/", include(("apps.kanban.urls", "kanban"), namespace="kanban")),
    path("sla/", include(("apps.sla.urls", "sla"), namespace="sla")),
    path(
        "monitoramento/",
        include(("apps.monitoramento.urls", "monitoramento"), namespace="monitoramento"),
    ),
    path("backup/", include(("apps.backup.urls", "backup"), namespace="backup")),
    path(
        "email-marketing/",
        include(("apps.email_marketing.urls", "email_marketing"), namespace="email_marketing"),
    ),
    path("cupons/", include(("apps.cupons.urls", "cupons"), namespace="cupons")),
    path("blog/", include(("apps.blog.urls", "blog"), namespace="blog")),
    # O núcleo (dashboard) fica na raiz e deve vir por último.
    path("", include(("apps.nucleo.urls", "nucleo"), namespace="nucleo")),
]


# ---------------------------------------------------------------------------
# Handlers de erro — renderizam templates em 'erros/'
# ---------------------------------------------------------------------------
def erro_400(request, exception=None):
    """Requisição inválida (400)."""
    return render(request, "erros/400.html", status=400)


def erro_403(request, exception=None):
    """Acesso negado (403)."""
    return render(request, "erros/403.html", status=403)


def erro_404(request, exception=None):
    """Página não encontrada (404)."""
    return render(request, "erros/404.html", status=404)


def erro_500(request):
    """Erro interno do servidor (500)."""
    return render(request, "erros/500.html", status=500)


handler400 = "config.urls.erro_400"
handler403 = "config.urls.erro_403"
handler404 = "config.urls.erro_404"
handler500 = "config.urls.erro_500"


# Estáticos: WhiteNoise serve em produção; em DEBUG usamos os helpers do Django.
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()

# Mídia (uploads: logo do sistema, fotos de perfil) — servida em TODOS os
# ambientes para funcionar tanto no Compose local (com Nginx) quanto no
# EasyPanel (contêiner único atrás do proxy da plataforma). Quando há Nginx,
# ele intercepta /media/ antes de chegar à aplicação (mais rápido).
# ``serve`` usa ``safe_join`` (protege contra path traversal). Backups NÃO ficam
# em MEDIA: vão para BACKUPS_DIR e são baixados por view protegida.
from django.urls import re_path  # noqa: E402
from django.views.static import serve as _serve_media  # noqa: E402

_media_url = (settings.MEDIA_URL or "media/").lstrip("/")
urlpatterns += [
    re_path(
        rf"^{_media_url}(?P<path>.*)$",
        _serve_media,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

"""
Geração do arquivo estático **sitemap.xml na raiz do projeto** (utilitário portado).

NOTA: nesta fase o sitemap NÃO está ligado a nenhuma rota nem é chamado pelo
editor — o blog é gestão interna (somente staff), sem telas públicas. O arquivo é
mantido pronto para quando a fiação pública for decidida. Como não há telas
públicas ainda, ``build_sitemap_xml`` depende de ``blog:home``/``blog:post_detail``
etc., que só existirão quando as rotas públicas forem adicionadas.

A base da URL vem de ``settings.SITE_URL`` (URL completa, ex.: ``https://exemplo.com``).
"""
from xml.sax.saxutils import escape

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

# O sitemap.xml fica na raiz do projeto (BASE_DIR) e é servido em /sitemap.xml.
SITEMAP_PATH = settings.BASE_DIR / "sitemap.xml"


def default_base_url():
    """URL base do site a partir de ``settings.SITE_URL`` (já é URL completa)."""
    return (getattr(settings, "SITE_URL", "") or "http://localhost:8000").rstrip("/")


def _entry(base_url, location, lastmod=None, changefreq=None, priority=None):
    lines = [f"    <loc>{escape(base_url + location)}</loc>"]
    if lastmod:
        lines.append(f"    <lastmod>{lastmod:%Y-%m-%d}</lastmod>")
    if changefreq:
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
    if priority is not None:
        lines.append(f"    <priority>{priority}</priority>")
    return "  <url>\n" + "\n".join(lines) + "\n  </url>"


def build_sitemap_xml(base_url=None):
    """Monta o XML do sitemap com todas as URLs existentes no blog."""
    from apps.blog.models import Category, Post, Tag  # import tardio (evita ciclos)

    base_url = (base_url or default_base_url()).rstrip("/")
    entries = [_entry(base_url, reverse("blog:home"), timezone.now(), "daily", "1.0")]

    for post in Post.published.all():
        entries.append(_entry(base_url, post.get_absolute_url(), post.updated_at, "weekly", "0.8"))
    for category in Category.objects.all():
        entries.append(_entry(base_url, category.get_absolute_url(), None, "weekly", "0.5"))
    for tag in Tag.objects.all():
        entries.append(_entry(base_url, tag.get_absolute_url(), None, "weekly", "0.4"))

    body = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def generate_sitemap_file(base_url=None):
    """(Re)escreve o sitemap.xml na raiz do projeto e devolve o conteúdo."""
    xml = build_sitemap_xml(base_url)
    try:
        SITEMAP_PATH.write_text(xml, encoding="utf-8")
    except OSError:
        # Não derruba a ação do editor se o disco estiver somente-leitura.
        pass
    return xml

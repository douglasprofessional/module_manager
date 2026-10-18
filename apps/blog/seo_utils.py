"""
Ferramentas de apoio ao SEO/GEO usadas em modelos, views e no editor:
  - extração de texto e contagem de palavras
  - tempo de leitura
  - geração automática de resumo/meta
  - "aplicação de melhores práticas": pós-processa o HTML do conteúdo
    (lazy-loading em imagens, rel seguro em links externos, âncoras em títulos)
  - montagem do JSON-LD (Article) para dados estruturados

Portado de ``djangopress`` sem alterações de lógica; a única adaptação é o nome
de exibição do autor, que passa a usar ``contas.Usuario.get_full_name()``.
"""
import re

import bleach
from bs4 import BeautifulSoup

WORDS_PER_MINUTE = 200

# Allowlist de tags/atributos permitidos no conteúdo dos posts.
# Tudo fora disso (script, iframe, on*=, style…) é removido na sanitização.
ALLOWED_TAGS = [
    "p", "br", "hr", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "a", "img", "strong", "b", "em", "i", "u", "s",
    "blockquote", "code", "pre", "figure", "figcaption", "span", "div",
    "table", "thead", "tbody", "tr", "th", "td", "caption",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height", "loading", "decoding"],
    "*": ["id"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(html):
    """Remove markup ativo (script, iframe, handlers on*=, javascript: …)."""
    if not html or not html.strip():
        return html
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def _soup(html):
    return BeautifulSoup(html or "", "html.parser")


def strip_html(html):
    return _soup(html).get_text(" ", strip=True)


def word_count(html):
    text = strip_html(html)
    return len([w for w in re.split(r"\s+", text) if w])


def reading_time_minutes(html):
    return max(1, round(word_count(html) / WORDS_PER_MINUTE))


def truncate(text, length=160):
    text = (text or "").strip()
    if len(text) <= length:
        return text
    return text[: length - 1].rsplit(" ", 1)[0].rstrip() + "…"


def make_excerpt(html, length=160):
    """Cria um resumo a partir do primeiro parágrafo (ou do texto)."""
    soup = _soup(html)
    first_p = soup.find("p")
    source = first_p.get_text(" ", strip=True) if first_p else soup.get_text(" ", strip=True)
    return truncate(source, length)


def slugify_heading(text):
    base = re.sub(r"[^\w\s-]", "", (text or "").lower()).strip()
    return re.sub(r"[\s_]+", "-", base)[:60] or "secao"


def enhance_content_html(html):
    """
    Aplica melhores práticas de front-end ao HTML do conteúdo:
      - <img> ganham loading="lazy" e decoding="async"
      - links externos (target=_blank) ganham rel="noopener noreferrer"
      - títulos h2/h3/h4 recebem um id (âncora) se não tiverem
    Retorna o HTML transformado (string).
    """
    if not html or not html.strip():
        return html
    # 1) Sanitiza (remove qualquer markup ativo) ANTES de confiar no HTML.
    html = sanitize_html(html)
    soup = _soup(html)

    for img in soup.find_all("img"):
        img.attrs.setdefault("loading", "lazy")
        img.attrs.setdefault("decoding", "async")

    for a in soup.find_all("a"):
        target = a.get("target")
        href = a.get("href", "")
        if target == "_blank" or href.startswith("http"):
            rel = set((a.get("rel") or []))
            rel.update({"noopener", "noreferrer"})
            a["rel"] = " ".join(sorted(rel))

    # Semeia com os IDs já presentes para não gerar duplicatas.
    used_ids = {tag["id"] for tag in soup.find_all(id=True)}
    for h in soup.find_all(["h2", "h3", "h4"]):
        if not h.get("id"):
            anchor = slugify_heading(h.get_text())
            unique = anchor
            i = 2
            while unique in used_ids:
                unique = f"{anchor}-{i}"
                i += 1
            h["id"] = unique
            used_ids.add(unique)

    return str(soup)


def _nome_autor(post, organization):
    """Nome de exibição do autor (usa ``get_full_name`` do usuário da plataforma)."""
    if not post.author:
        return organization
    try:
        return post.author.get_full_name()
    except Exception:
        return organization


def build_article_jsonld(post, absolute_url, image_url, site_name, organization):
    """Monta o dicionário JSON-LD (schema.org/Article) para dados estruturados."""
    author_name = _nome_autor(post, organization)
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": truncate(post.title, 110),
        "description": post.display_meta_description,
        "articleBody": strip_html(post.content)[:5000],
        "wordCount": post.word_count,
        "url": absolute_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": absolute_url},
        "author": {"@type": "Person", "name": author_name},
        "publisher": {"@type": "Organization", "name": organization or site_name},
        "inLanguage": "pt-BR",
    }
    if image_url:
        data["image"] = [image_url]
    if post.published_at:
        data["datePublished"] = post.published_at.isoformat()
    if post.updated_at:
        data["dateModified"] = post.updated_at.isoformat()
    if post.focus_keyword:
        data["keywords"] = post.focus_keyword
    return data

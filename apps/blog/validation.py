"""
Motor de validação de melhores práticas — executado no SERVIDOR a cada vez que
o autor clica em Salvar / Publicar / Agendar / Enviar para revisão, e também
via AJAX (feedback ao vivo no editor).

Três dimensões:
  • SEO           — otimização para buscadores (Google/Bing)
  • GEO           — Generative Engine Optimization (ser citado por IAs/LLMs)
  • Acessibilidade— WCAG 2.1 + atributos ARIA

Cada checagem tem: id, label, status (pass/warn/fail), message, critical.
Checagens `critical` que falham BLOQUEIAM a publicação/agendamento.
"""
import re

from bs4 import BeautifulSoup
from django.utils import timezone

PASS, WARN, FAIL = "pass", "warn", "fail"

# Textos de link genéricos (ruins para SEO e acessibilidade).
GENERIC_LINK_TEXT = {
    "clique aqui", "clique", "aqui", "saiba mais", "leia mais", "veja mais",
    "link", "este link", "click here", "read more", "here", "more", "this link",
}
# Textos alternativos genéricos demais.
GENERIC_ALT = {"imagem", "image", "foto", "picture", "photo", "img", "banner"}
# Início de perguntas (ajuda GEO — conteúdo em formato de resposta).
QUESTION_STARTS = {
    "como", "o que", "porque", "por que", "quando", "onde", "quais", "qual",
    "quem", "quanto", "how", "what", "why", "when", "where", "which", "who",
}

# --- Regras de UI: rótulos das dimensões ---
DIMENSIONS = ("seo", "geo", "accessibility")


def _check(cid, label, status, message, critical=False, weight=1):
    return {
        "id": cid,
        "label": label,
        "status": status,
        "message": message,
        "critical": critical,
        "weight": weight,
    }


def _group(name, checks):
    total = sum(c["weight"] for c in checks) or 1
    got = sum(
        c["weight"] * (1.0 if c["status"] == PASS else 0.5 if c["status"] == WARN else 0.0)
        for c in checks
    )
    score = round(100 * got / total)
    return {
        "name": name,
        "score": score,
        "rating": "good" if score >= 80 else ("ok" if score >= 50 else "bad"),
        "passed": sum(1 for c in checks if c["status"] == PASS),
        "warnings": sum(1 for c in checks if c["status"] == WARN),
        "failed": sum(1 for c in checks if c["status"] == FAIL),
        "total": len(checks),
        "checks": checks,
    }


# --------------------------------------------------------------------------- #
# Construção do contexto (parse único do HTML)
# --------------------------------------------------------------------------- #
def _build_context(payload):
    html = payload.get("content") or ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    words = [w for w in re.split(r"\s+", text) if w]
    first_p = soup.find("p")
    first_text = first_p.get_text(" ", strip=True) if first_p else text[:400]
    return {
        "payload": payload,
        "soup": soup,
        "text": text,
        "text_lower": text.lower(),
        "words": words,
        "word_count": len(words),
        "first_text": first_text,
        "first_text_lower": first_text.lower(),
        "headings": soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]),
        "images": soup.find_all("img"),
        "links": soup.find_all("a"),
        "lists": soup.find_all(["ul", "ol"]),
        "tables": soup.find_all("table"),
        "keyword": (payload.get("focus_keyword") or "").strip().lower(),
        "seo_title": (payload.get("meta_title") or payload.get("title") or "").strip(),
    }


# --------------------------------------------------------------------------- #
# Dimensão: SEO
# --------------------------------------------------------------------------- #
def _analyze_seo(ctx):
    p = ctx["payload"]
    checks = []
    title = (p.get("title") or "").strip()
    seo_title = ctx["seo_title"]
    kw = ctx["keyword"]

    # Título
    if not title:
        checks.append(_check("title", "Título preenchido", FAIL, "O post precisa de um título.", critical=True))
    else:
        n = len(seo_title)
        if 30 <= n <= 60:
            checks.append(_check("title", "Tamanho do título", PASS, f"Título com {n} caracteres (ideal 30–60)."))
        elif n < 30:
            checks.append(_check("title", "Tamanho do título", WARN, f"Título curto ({n}). Considere 30–60 caracteres."))
        else:
            checks.append(_check("title", "Tamanho do título", WARN, f"Título longo ({n}). O Google corta acima de ~60."))

    # Meta description
    md = (p.get("meta_description") or "").strip()
    if not md:
        checks.append(_check("meta_desc", "Meta description", FAIL, "Defina uma meta description (120–160 caracteres)."))
    else:
        n = len(md)
        if 120 <= n <= 160:
            checks.append(_check("meta_desc", "Meta description", PASS, f"Meta description com {n} caracteres."))
        else:
            checks.append(_check("meta_desc", "Meta description", WARN, f"Meta description com {n} caracteres (ideal 120–160)."))

    # Slug (URL)
    slug = (p.get("slug") or "").strip()
    if not slug:
        checks.append(_check("slug", "URL (slug)", WARN, "Slug será gerado a partir do título ao salvar."))
    elif re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug) and len(slug) <= 75:
        checks.append(_check("slug", "URL (slug)", PASS, "Slug amigável e bem formatado."))
    else:
        checks.append(_check("slug", "URL (slug)", FAIL, "Slug inválido: use apenas minúsculas, números e hífens.", critical=True))

    # Palavra-chave foco
    if not kw:
        checks.append(_check("focus_kw", "Palavra-chave foco", WARN, "Defina uma palavra-chave foco para orientar o SEO."))
    else:
        checks.append(_check("focus_kw", "Palavra-chave foco", PASS, f"Palavra-chave foco: “{kw}”."))
        # Presença nos lugares certos
        checks.append(_kw_in("kw_title", "Palavra-chave no título", kw, seo_title.lower()))
        checks.append(_kw_in("kw_first_p", "Palavra-chave no 1º parágrafo", kw, ctx["first_text_lower"]))
        checks.append(_kw_in("kw_meta", "Palavra-chave na meta description", kw, md.lower()))
        subs = " ".join(h.get_text(" ", strip=True).lower() for h in ctx["headings"])
        checks.append(_kw_in("kw_subheading", "Palavra-chave em subtítulo", kw, subs))
        checks.append(_kw_in("kw_slug", "Palavra-chave na URL", kw.replace(" ", "-"), slug))
        # Densidade
        density = _keyword_density(kw, ctx)
        if density == 0:
            checks.append(_check("kw_density", "Densidade da palavra-chave", WARN, "Palavra-chave não aparece no corpo do texto."))
        elif 0.3 <= density <= 3.0:
            checks.append(_check("kw_density", "Densidade da palavra-chave", PASS, f"Densidade de {density:.1f}% (saudável)."))
        else:
            msg = "baixa" if density < 0.3 else "alta (evite keyword stuffing)"
            checks.append(_check("kw_density", "Densidade da palavra-chave", WARN, f"Densidade {msg}: {density:.1f}%."))

    # Tamanho do conteúdo
    wc = ctx["word_count"]
    if wc >= 300:
        checks.append(_check("length", "Tamanho do conteúdo", PASS, f"{wc} palavras."))
    elif wc >= 150:
        checks.append(_check("length", "Tamanho do conteúdo", WARN, f"Apenas {wc} palavras. Ideal ≥ 300."))
    else:
        checks.append(_check("length", "Tamanho do conteúdo", FAIL, f"Conteúdo muito curto ({wc} palavras)."))

    # Links internos/externos
    if ctx["links"]:
        checks.append(_check("links", "Links no conteúdo", PASS, f"{len(ctx['links'])} link(s) encontrados."))
    else:
        checks.append(_check("links", "Links no conteúdo", WARN, "Adicione links internos/externos relevantes."))

    # Imagem de capa
    if p.get("has_featured_image"):
        checks.append(_check("featured", "Imagem de capa", PASS, "Imagem de capa definida."))
    else:
        checks.append(_check("featured", "Imagem de capa", WARN, "Defina uma imagem de capa (melhora CTR e compartilhamento)."))

    return _group("seo", checks)


def _kw_in(cid, label, needle, haystack):
    if needle and needle in (haystack or ""):
        return _check(cid, label, PASS, "Encontrada. ✓")
    return _check(cid, label, WARN, "Não encontrada neste local.")


def _keyword_density(kw, ctx):
    if not kw or ctx["word_count"] == 0:
        return 0.0
    # Conta a palavra-chave como palavra inteira (evita casar dentro de outras).
    occurrences = len(re.findall(r"\b" + re.escape(kw) + r"\b", ctx["text_lower"]))
    kw_words = max(1, len(kw.split()))
    return round(100 * occurrences * kw_words / ctx["word_count"], 2)


# --------------------------------------------------------------------------- #
# Dimensão: GEO (Generative Engine Optimization)
# --------------------------------------------------------------------------- #
def _analyze_geo(ctx):
    p = ctx["payload"]
    checks = []

    # Resumo/TL;DR — respostas diretas ajudam LLMs a citar o conteúdo
    excerpt = (p.get("excerpt") or "").strip()
    if excerpt:
        checks.append(_check("summary", "Resumo (TL;DR)", PASS, "Resumo presente — facilita a extração por IAs."))
    else:
        checks.append(_check("summary", "Resumo (TL;DR)", FAIL, "Adicione um resumo respondendo direto à intenção do leitor."))

    # Parágrafo inicial que responde de imediato
    first_words = len([w for w in ctx["first_text"].split() if w])
    if first_words >= 40:
        checks.append(_check("answer_first", "Resposta logo no início", PASS, "O 1º parágrafo já entrega valor."))
    else:
        checks.append(_check("answer_first", "Resposta logo no início", WARN, "Comece respondendo à pergunta central do post."))

    # Subtítulos em forma de pergunta
    if _has_question_heading(ctx["headings"]):
        checks.append(_check("questions", "Subtítulos em forma de pergunta", PASS, "Bom para featured snippets e IAs."))
    else:
        checks.append(_check("questions", "Subtítulos em forma de pergunta", WARN, "Use subtítulos como perguntas (ex.: “Como fazer X?”)."))

    # Conteúdo estruturado (listas/tabelas) — fácil de extrair
    if ctx["lists"] or ctx["tables"]:
        checks.append(_check("structured", "Conteúdo estruturado", PASS, "Listas/tabelas facilitam a extração de fatos."))
    else:
        checks.append(_check("structured", "Conteúdo estruturado", WARN, "Inclua listas ou tabelas com pontos-chave."))

    # Dados/estatísticas citáveis
    if re.search(r"\d", ctx["text"]):
        checks.append(_check("stats", "Dados e números", PASS, "Há números/estatísticas citáveis."))
    else:
        checks.append(_check("stats", "Dados e números", WARN, "Inclua dados/estatísticas — IAs valorizam fatos verificáveis."))

    # Fontes/citações externas (autoridade / E-E-A-T)
    external = [a for a in ctx["links"] if (a.get("href") or "").startswith("http")]
    if external:
        checks.append(_check("citations", "Fontes externas", PASS, f"{len(external)} referência(s) externa(s)."))
    else:
        checks.append(_check("citations", "Fontes externas", WARN, "Cite fontes confiáveis para reforçar a autoridade."))

    # Autoria (E-E-A-T)
    if (p.get("author_name") or "").strip():
        checks.append(_check("author", "Autoria identificada", PASS, "Autor definido (sinal de E-E-A-T)."))
    else:
        checks.append(_check("author", "Autoria identificada", WARN, "Associe o post a um autor."))

    # Dados estruturados (JSON-LD é gerado automaticamente)
    if (p.get("title") or "").strip():
        checks.append(_check("jsonld", "Dados estruturados (JSON-LD)", PASS, "Schema.org/Article será incluído automaticamente."))
    else:
        checks.append(_check("jsonld", "Dados estruturados (JSON-LD)", WARN, "Título necessário para gerar o JSON-LD."))

    return _group("geo", checks)


def _has_question_heading(headings):
    for h in headings:
        t = h.get_text(" ", strip=True).lower()
        if t.endswith("?"):
            return True
        if any(t.startswith(q + " ") for q in QUESTION_STARTS):
            return True
    return False


# --------------------------------------------------------------------------- #
# Dimensão: Acessibilidade (WCAG + ARIA)
# --------------------------------------------------------------------------- #
def _analyze_accessibility(ctx):
    p = ctx["payload"]
    checks = []

    # Texto alternativo em TODAS as imagens do conteúdo
    imgs = ctx["images"]
    missing_alt = [img for img in imgs if not (img.get("alt") or "").strip()]
    generic_alt = [img for img in imgs if (img.get("alt") or "").strip().lower() in GENERIC_ALT]
    if not imgs:
        checks.append(_check("img_alt", "Texto alternativo (imagens)", PASS, "Sem imagens no corpo do texto."))
    elif missing_alt:
        checks.append(_check("img_alt", "Texto alternativo (imagens)", FAIL,
                             f"{len(missing_alt)} imagem(ns) sem atributo alt.", critical=True))
    elif generic_alt:
        checks.append(_check("img_alt", "Texto alternativo (imagens)", WARN,
                             "Alt genérico demais (ex.: “imagem”). Descreva o conteúdo."))
    else:
        checks.append(_check("img_alt", "Texto alternativo (imagens)", PASS, "Todas as imagens têm alt descritivo."))

    # Alt da imagem de capa
    if p.get("has_featured_image") and not (p.get("featured_image_alt") or "").strip():
        checks.append(_check("featured_alt", "Alt da imagem de capa", FAIL,
                             "Descreva a imagem de capa no campo de texto alternativo.", critical=True))
    elif p.get("has_featured_image"):
        checks.append(_check("featured_alt", "Alt da imagem de capa", PASS, "Capa com texto alternativo."))

    # Hierarquia de títulos: não pode haver <h1> no corpo (o H1 é o título da página)
    levels = [int(h.name[1]) for h in ctx["headings"]]
    if any(l == 1 for l in levels):
        checks.append(_check("headings_h1", "Sem H1 no conteúdo", FAIL,
                             "O corpo não deve conter <h1> (ele é o título da página). Use H2+.", critical=True))
    else:
        checks.append(_check("headings_h1", "Sem H1 no conteúdo", PASS, "Nenhum H1 duplicado no corpo."))

    # Sem pular níveis de título (ex.: H2 -> H4)
    if _has_heading_skip(levels):
        checks.append(_check("headings_order", "Hierarquia de títulos", WARN,
                             "Evite pular níveis (ex.: de H2 direto para H4)."))
    else:
        checks.append(_check("headings_order", "Hierarquia de títulos", PASS, "Hierarquia de títulos consistente."))

    # Links descritivos + links vazios
    bad_links = []
    empty_links = []
    for a in ctx["links"]:
        label = a.get_text(" ", strip=True).lower()
        aria = (a.get("aria-label") or "").strip()
        if not label and not aria and not a.find("img"):
            empty_links.append(a)
        elif label in GENERIC_LINK_TEXT:
            bad_links.append(a)
    if empty_links:
        checks.append(_check("links_empty", "Links com rótulo acessível", FAIL,
                             f"{len(empty_links)} link(s) sem texto nem aria-label.", critical=True))
    else:
        checks.append(_check("links_empty", "Links com rótulo acessível", PASS, "Todos os links têm rótulo."))
    if bad_links:
        checks.append(_check("links_generic", "Textos de link descritivos", WARN,
                             "Evite “clique aqui”/“saiba mais”. Descreva o destino."))
    else:
        checks.append(_check("links_generic", "Textos de link descritivos", PASS, "Textos de link descritivos."))

    # Tabelas com cabeçalho
    if ctx["tables"]:
        no_headers = [t for t in ctx["tables"] if not t.find("th")]
        if no_headers:
            checks.append(_check("table_headers", "Tabelas com cabeçalho", WARN,
                                 "Use <th> em tabelas de dados para leitores de tela."))
        else:
            checks.append(_check("table_headers", "Tabelas com cabeçalho", PASS, "Tabelas com <th>."))

    # Marcos ARIA / idioma (garantidos pelo template base)
    checks.append(_check("landmarks", "Marcos ARIA e idioma", PASS,
                         "O tema inclui <html lang>, <nav>, <main>, <article> e rótulos ARIA."))

    return _group("accessibility", checks)


def _has_heading_skip(levels):
    prev = None
    for lvl in levels:
        if prev is not None and lvl > prev + 1:
            return True
        prev = lvl
    return False


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def run_validation(payload):
    """
    `payload` é um dict com as chaves:
        title, meta_title, meta_description, slug, focus_keyword, excerpt,
        content (HTML), has_featured_image (bool), featured_image_alt,
        author_name, site (opcional/None)
    Retorna o relatório completo (serializável em JSON).
    """
    ctx = _build_context(payload)
    seo = _analyze_seo(ctx)
    geo = _analyze_geo(ctx)
    a11y = _analyze_accessibility(ctx)

    groups = {"seo": seo, "geo": geo, "accessibility": a11y}
    overall = round((seo["score"] + geo["score"] + a11y["score"]) / 3)

    blocking = [
        c["label"]
        for g in groups.values()
        for c in g["checks"]
        if c["critical"] and c["status"] == FAIL
    ]

    return {
        "seo": seo,
        "geo": geo,
        "accessibility": a11y,
        "overall_score": overall,
        "can_publish": not blocking,
        "blocking_issues": blocking,
        "generated_at": timezone.now().isoformat(),
    }


def build_payload_from_post(post, site=None):
    return {
        "title": post.title,
        "meta_title": post.meta_title,
        "meta_description": post.meta_description,
        "slug": post.slug,
        "focus_keyword": post.focus_keyword,
        "excerpt": post.excerpt,
        "content": post.content,
        "has_featured_image": bool(post.featured_image),
        "featured_image_alt": post.featured_image_alt,
        "author_name": post.author.get_full_name() if post.author else "",
        "site": site,
    }


def validate_post(post, site=None):
    return run_validation(build_payload_from_post(post, site))

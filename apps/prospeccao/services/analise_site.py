"""Análise heurística de HTML de sites de empresas.

Recebe o HTML já baixado (sempre via ``seguranca_rede.requisicao_segura``) e
extrai sinais de qualidade e contato SEM libs pesadas de parsing — apenas
``re`` e utilidades da stdlib.

Saída de :func:`analisar_html` (dict com chaves fixas):
``titulo, meta_description, tem_h1, tem_viewport, score_seo, apenas_instagram,
site_desatualizado, emails, instagram, whatsapp, dominio``.
"""
from __future__ import annotations

import html as _html
import logging
import re
from datetime import date
from urllib.parse import urlparse

logger = logging.getLogger("modulos.prospeccao.analise_site")

# ---------------------------------------------------------------------------
# Extração de domínio (tldextract offline; fallback para urlparse)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - depende do pacote instalado
    import tldextract

    # ``suffix_list_urls=()`` força o uso do snapshot embutido: sem rede.
    _extrator_dominio = tldextract.TLDExtract(suffix_list_urls=())
except Exception:  # noqa: BLE001 - degrada para urlparse se indisponível
    _extrator_dominio = None


# ---------------------------------------------------------------------------
# Expressões regulares compiladas
# ---------------------------------------------------------------------------
_RE_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_RE_META_NAME = re.compile(r"""name\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE)
_RE_META_CONTENT = re.compile(r"""content\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
_RE_H1 = re.compile(r"<h1[\s/>]", re.IGNORECASE)
_RE_SCRIPT_STYLE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_RE_TAGS = re.compile(r"(?s)<[^>]+>")

_RE_EMAIL = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
)
_RE_INSTAGRAM = re.compile(
    r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)", re.IGNORECASE
)
_RE_WA_ME = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?[^\"'\s]*?phone=)\+?(\d{8,15})",
    re.IGNORECASE,
)
_RE_TEL_BR = re.compile(
    r"(?:\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-.\s]?\d{4}"
)
_RE_ANO = re.compile(r"\b(19|20)\d{2}\b")
_RE_COPYRIGHT = re.compile(
    r"(?:©|&copy;|copyright|todos os direitos)\D{0,20}((?:19|20)\d{2})",
    re.IGNORECASE,
)

# Handles do Instagram que são rotas/seções, não perfis.
_INSTAGRAM_RESERVADOS = frozenset(
    {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "developer"}
)
# "TLDs" que na verdade são extensões de arquivo (evita falso email tipo logo@2x.png).
_EXT_FALSAS = frozenset(
    {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "ico", "bmp", "mp4", "pdf", "woff", "woff2"}
)


def _texto_visivel(html: str) -> str:
    """Remove script/style e tags, devolvendo o texto aproximado da página."""
    sem_script = _RE_SCRIPT_STYLE.sub(" ", html)
    sem_tags = _RE_TAGS.sub(" ", sem_script)
    return _html.unescape(re.sub(r"\s+", " ", sem_tags)).strip()


def _meta_conteudo(html: str, nome: str) -> str:
    """Retorna o ``content`` da primeira <meta name="nome"> encontrada."""
    alvo = nome.lower()
    for m in _RE_META.finditer(html):
        tag = m.group(0)
        nm = _RE_META_NAME.search(tag)
        if not nm or nm.group(1).strip().lower() != alvo:
            continue
        cont = _RE_META_CONTENT.search(tag)
        if cont:
            valor = cont.group(1) if cont.group(1) is not None else cont.group(2)
            return _html.unescape((valor or "").strip())
        return ""
    return ""


def _dominio(url: str) -> str:
    """Extrai o domínio registrável da URL (ex.: 'padaria.com.br')."""
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    if _extrator_dominio is not None:
        try:
            ext = _extrator_dominio(url)
            if ext.domain and ext.suffix:
                return f"{ext.domain}.{ext.suffix}".lower()
            if ext.domain:
                return ext.domain.lower()
        except Exception:  # noqa: BLE001 - fallback abaixo
            pass
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _emails(html: str) -> set[str]:
    """Extrai e-mails plausíveis, descartando falsos positivos comuns."""
    achados: set[str] = set()
    for bruto in _RE_EMAIL.findall(html):
        email = bruto.strip().strip(".").lower()
        dominio = email.rsplit("@", 1)[-1]
        ext = dominio.rsplit(".", 1)[-1]
        if ext in _EXT_FALSAS:
            continue
        if ".." in email or email.startswith("."):
            continue
        achados.add(email)
    return achados


def _instagram(html: str) -> str:
    """Retorna o primeiro handle '@perfil' do Instagram, se houver."""
    for handle in _RE_INSTAGRAM.findall(html):
        limpo = handle.strip("/").strip()
        if not limpo or limpo.lower() in _INSTAGRAM_RESERVADOS:
            continue
        return "@" + limpo
    return ""


def _formatar_whatsapp(bruto: str) -> str:
    """Normaliza dígitos para o formato '+55 (DD) NNNNN-NNNN'."""
    d = re.sub(r"\D", "", bruto)
    if not d:
        return ""
    if len(d) in (10, 11):  # DDD + número, sem código do país
        d = "55" + d
    if not d.startswith("55") or len(d) < 12:
        return "+" + d  # país desconhecido/ formato incomum
    resto = d[2:]
    ddd, numero = resto[:2], resto[2:]
    if len(numero) == 9:
        linha = f"{numero[:5]}-{numero[5:]}"
    elif len(numero) == 8:
        linha = f"{numero[:4]}-{numero[4:]}"
    else:
        linha = numero
    return f"+55 ({ddd}) {linha}"


def _whatsapp(html: str, texto: str) -> str:
    """Extrai um número de WhatsApp de links wa.me/api.whatsapp ou telefone BR."""
    m = _RE_WA_ME.search(html)
    if m:
        return _formatar_whatsapp(m.group(1))
    m = _RE_TEL_BR.search(texto)
    if m:
        return _formatar_whatsapp(m.group(0))
    return ""


def _score_seo(tem_titulo: bool, tem_desc: bool, tem_h1: bool, tem_viewport: bool, tem_https: bool) -> int:
    """Heurística simples de SEO (0..100)."""
    score = 0
    if tem_titulo:
        score += 25
    if tem_desc:
        score += 25
    if tem_h1:
        score += 20
    if tem_viewport:
        score += 15
    if tem_https:
        score += 15
    return min(score, 100)


def _site_desatualizado(tem_viewport: bool, tem_https: bool, html: str) -> bool:
    """Heurística de site desatualizado (ano antigo, sem viewport, sem https)."""
    ano_atual = date.today().year
    ano_antigo = False

    mcopy = _RE_COPYRIGHT.search(html)
    if mcopy:
        try:
            if int(mcopy.group(1)) <= ano_atual - 3:
                ano_antigo = True
        except ValueError:
            pass
    else:
        # Sem marcador de copyright explícito: olha o maior ano plausível citado.
        # ``finditer`` + ``group(0)`` devolve o ano inteiro (ex.: "2018").
        anos = [int(m.group(0)) for m in _RE_ANO.finditer(html)]
        plausiveis = [a for a in anos if a <= ano_atual + 1]
        if plausiveis and max(plausiveis) <= ano_atual - 3:
            ano_antigo = True

    fracos = (0 if tem_viewport else 1) + (0 if tem_https else 1)
    return ano_antigo or fracos >= 2


def _apenas_instagram(url: str, html: str, texto: str, tem_instagram: bool) -> bool:
    """Detecta páginas que só apontam para Instagram/Linktree (pouca substância)."""
    dominio = _dominio(url)
    if dominio in {"linktr.ee", "instagram.com", "instagr.am", "beacons.ai", "linkbio.co"}:
        return True
    social = tem_instagram or "linktr.ee" in html.lower() or "linktree" in html.lower()
    return bool(social and len(texto) < 600)


def analisar_html(html: str, url: str) -> dict:
    """Analisa o HTML de um site e devolve sinais de SEO, atualização e contato.

    Args:
        html: conteúdo HTML já baixado (via fetcher seguro).
        url: URL final de onde o HTML veio (usada p/ domínio e HTTPS).

    Returns:
        dict com as chaves fixas descritas no módulo. ``emails`` é um ``set``;
        os demais campos textuais vêm como ``str`` ("" quando ausentes).
    """
    html = html or ""
    texto = _texto_visivel(html)
    tem_https = url.lower().startswith("https://")

    titulo_m = _RE_TITULO.search(html)
    titulo = _html.unescape(re.sub(r"\s+", " ", titulo_m.group(1)).strip()) if titulo_m else ""
    meta_description = _meta_conteudo(html, "description")
    tem_h1 = bool(_RE_H1.search(html))
    tem_viewport = bool(_meta_conteudo(html, "viewport")) or bool(
        re.search(r"""name\s*=\s*['"]viewport['"]""", html, re.IGNORECASE)
    )

    instagram = _instagram(html)
    resultado = {
        "titulo": titulo,
        "meta_description": meta_description,
        "tem_h1": tem_h1,
        "tem_viewport": tem_viewport,
        "score_seo": _score_seo(bool(titulo), bool(meta_description), tem_h1, tem_viewport, tem_https),
        "apenas_instagram": _apenas_instagram(url, html, texto, bool(instagram)),
        "site_desatualizado": _site_desatualizado(tem_viewport, tem_https, html),
        "emails": _emails(html),
        "instagram": instagram,
        "whatsapp": _whatsapp(html, texto),
        "dominio": _dominio(url),
    }
    logger.debug(
        "Análise de %s: seo=%s desatualizado=%s apenas_ig=%s",
        resultado["dominio"],
        resultado["score_seo"],
        resultado["site_desatualizado"],
        resultado["apenas_instagram"],
    )
    return resultado

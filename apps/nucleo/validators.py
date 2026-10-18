"""Validadores de upload reutilizáveis do núcleo (segurança de arquivos).

Aplicados a fotos de perfil e ao logo do sistema. Validam a EXTENSÃO, o
tamanho máximo e uma checagem simples de conteúdo (assinatura/`magic bytes`)
para reduzir a chance de um arquivo malicioso ser aceito apenas por ter a
extensão trocada. Nunca confiam no ``content_type`` enviado pelo cliente.

Uploads são gravados em ``MEDIA_ROOT`` (fora da árvore de código) — ver
``settings.MEDIA_ROOT`` — e servidos por rota dedicada (Nginx em produção).
"""
from __future__ import annotations

import os

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Limite padrão de tamanho para imagens enviadas pela interface (2 MB).
TAMANHO_MAXIMO_PADRAO = 2 * 1024 * 1024

# Extensões aceitas para fotos (raster) e para o logo (raster + SVG vetorial).
EXTENSOES_FOTO = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
EXTENSOES_LOGO = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

# Assinaturas de arquivo (primeiros bytes) por formato raster conhecido.
_ASSINATURAS = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # 'RIFF'....'WEBP' — checagem simplificada do prefixo.
}


def _extensao(nome: str) -> str:
    """Retorna a extensão do arquivo em minúsculas (com o ponto)."""
    return os.path.splitext(nome or "")[1].lower()


def _validar_tamanho(arquivo, maximo: int) -> None:
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > maximo:
        raise ValidationError(
            _("Arquivo muito grande (máx. %(mb)s MB).")
            % {"mb": round(maximo / (1024 * 1024), 1)},
            code="arquivo_grande",
        )


def _validar_conteudo_raster(arquivo) -> None:
    """Confere os primeiros bytes de uma imagem raster contra assinaturas conhecidas."""
    try:
        posicao = arquivo.tell()
    except Exception:
        posicao = None
    try:
        cabecalho = arquivo.read(12)
    finally:
        if posicao is not None:
            try:
                arquivo.seek(posicao)
            except Exception:
                pass
    if not cabecalho:
        return
    for assinatura in _ASSINATURAS:
        if cabecalho.startswith(assinatura):
            return
    raise ValidationError(
        _("O conteúdo do arquivo não corresponde a uma imagem válida."),
        code="conteudo_invalido",
    )


def _validar_svg(arquivo) -> None:
    """Bloqueia SVGs com scripts/handlers embutidos (vetor XSS conhecido)."""
    try:
        posicao = arquivo.tell()
    except Exception:
        posicao = None
    try:
        bruto = arquivo.read(65536)
    finally:
        if posicao is not None:
            try:
                arquivo.seek(posicao)
            except Exception:
                pass
    conteudo = (bruto or b"").lower()
    if b"<svg" not in conteudo:
        raise ValidationError(_("SVG inválido."), code="svg_invalido")
    proibidos = (b"<script", b"javascript:", b"onload=", b"onerror=", b"onclick=")
    if any(marca in conteudo for marca in proibidos):
        raise ValidationError(
            _("SVG com conteúdo executável não é permitido por segurança."),
            code="svg_inseguro",
        )


def validar_imagem_perfil(arquivo) -> None:
    """Valida a foto de perfil do usuário (somente formatos raster seguros)."""
    ext = _extensao(getattr(arquivo, "name", ""))
    if ext not in EXTENSOES_FOTO:
        raise ValidationError(
            _("Formato não permitido. Use: %(exts)s.")
            % {"exts": ", ".join(sorted(EXTENSOES_FOTO))},
            code="extensao_invalida",
        )
    _validar_tamanho(arquivo, TAMANHO_MAXIMO_PADRAO)
    _validar_conteudo_raster(arquivo)


def validar_logo(arquivo) -> None:
    """Valida o logo do sistema (raster ou SVG saneado)."""
    ext = _extensao(getattr(arquivo, "name", ""))
    if ext not in EXTENSOES_LOGO:
        raise ValidationError(
            _("Formato não permitido. Use: %(exts)s.")
            % {"exts": ", ".join(sorted(EXTENSOES_LOGO))},
            code="extensao_invalida",
        )
    _validar_tamanho(arquivo, TAMANHO_MAXIMO_PADRAO)
    if ext == ".svg":
        _validar_svg(arquivo)
    else:
        _validar_conteudo_raster(arquivo)

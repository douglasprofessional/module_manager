"""Modelos do módulo de backup (adendo 2 — MÓDULO 4).

Define o modelo ``Backup``, que representa um artefato de backup gerado pelo
sistema:

- ``tipo`` ``modulo``: dados de UM app (fixture Django ``.json.gz``, restaurável
  com ``loaddata``);
- ``tipo`` ``completo``: um ``.zip`` com o fixture de todos os dados, o dump
  nativo do banco e, opcionalmente, a árvore de ``MEDIA_ROOT``.

O campo ``arquivo`` guarda SEMPRE apenas o nome relativo dentro de
``settings.BACKUPS_DIR`` (nunca um caminho absoluto vindo do usuário). O acesso
ao arquivo em si passa por ``caminho_absoluto()``/``existe()`` e, no download,
por validação anti path traversal na view.

Enums em PT-BR via ``models.TextChoices``.
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("modulos.backup.models")

# Unidades para humanizar tamanhos de arquivo (base 1024).
_UNIDADES_TAMANHO = ("B", "KB", "MB", "GB", "TB", "PB")

# Mapa status -> classe de selo do design system (reutiliza tag-status--*).
_CLASSES_STATUS = {
    "pendente": "tag-status--pendente",
    "executando": "tag-status--executando",
    "concluido": "tag-status--concluida",
    "erro": "tag-status--erro",
}


class Backup(models.Model):
    """Um artefato de backup gerado pelo sistema (por módulo ou completo)."""

    class Tipo(models.TextChoices):
        MODULO = "modulo", _("Módulo")
        COMPLETO = "completo", _("Completo")
        EASYPANEL = "easypanel", _("Migração EasyPanel")

    class Status(models.TextChoices):
        PENDENTE = "pendente", _("Pendente")
        EXECUTANDO = "executando", _("Executando")
        CONCLUIDO = "concluido", _("Concluído")
        ERRO = "erro", _("Erro")

    tipo = models.CharField(
        _("tipo"),
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.MODULO,
    )
    escopo = models.CharField(
        _("escopo"),
        max_length=100,
        help_text=_("app_label do módulo (backup por módulo) ou 'completo'."),
    )
    rotulo = models.CharField(
        _("rótulo"),
        max_length=160,
        blank=True,
        default="",
        help_text=_("Descrição amigável (ex.: 'Kanban' ou 'Estrutura completa')."),
    )
    arquivo = models.CharField(
        _("arquivo"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Nome do arquivo relativo dentro de BACKUPS_DIR (nunca caminho absoluto)."),
    )
    tamanho_bytes = models.BigIntegerField(_("tamanho (bytes)"), default=0)
    checksum_sha256 = models.CharField(_("checksum SHA-256"), max_length=64, blank=True, default="")
    incluir_media = models.BooleanField(_("incluir mídia"), default=False)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )
    mensagem = models.TextField(_("mensagem"), blank=True, default="")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="backups_gerados",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    concluido_em = models.DateTimeField(_("concluído em"), null=True, blank=True)

    class Meta:
        verbose_name = _("backup")
        verbose_name_plural = _("backups")
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} — {self.rotulo or self.escopo}"

    # -- Apresentação -------------------------------------------------------
    def tamanho_texto(self) -> str:
        """Humaniza ``tamanho_bytes`` (ex.: ``1536`` -> ``"1.5 KB"``)."""
        tamanho = float(self.tamanho_bytes or 0)
        for unidade in _UNIDADES_TAMANHO:
            if tamanho < 1024 or unidade == _UNIDADES_TAMANHO[-1]:
                if unidade == "B":
                    return f"{int(tamanho)} {unidade}"
                return f"{tamanho:.1f} {unidade}"
            tamanho /= 1024
        return f"{tamanho:.1f} {_UNIDADES_TAMANHO[-1]}"

    def classe_status(self) -> str:
        """Classe do selo de status (reutiliza ``tag-status--*`` do design system)."""
        return _CLASSES_STATUS.get(self.status, "tag-status--pendente")

    # -- Acesso ao arquivo (uso interno) -----------------------------------
    def caminho_absoluto(self) -> Path:
        """Caminho absoluto do arquivo dentro de ``BACKUPS_DIR`` (uso interno)."""
        return Path(settings.BACKUPS_DIR) / self.arquivo

    def existe(self) -> bool:
        """Indica se o arquivo existe e está dentro de ``BACKUPS_DIR`` (defensivo)."""
        if not self.arquivo:
            return False
        try:
            base = Path(settings.BACKUPS_DIR).resolve()
            alvo = self.caminho_absoluto().resolve()
        except (OSError, ValueError, RuntimeError):
            return False
        dentro = alvo == base or base in alvo.parents
        return dentro and alvo.is_file()

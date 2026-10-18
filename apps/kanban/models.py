"""Modelos do módulo Kanban (adendo docs/SPEC_MODULOS.md — MÓDULO 1).

Define três modelos encadeados:

- ``Quadro``: um board de trabalho (ex.: "Comercial").
- ``Coluna``: uma raia do board (ex.: "Backlog", "Em andamento"), com limite de
  trabalho em progresso (WIP) opcional.
- ``Cartao``: uma tarefa dentro de uma coluna, com prioridade, responsável,
  prazo e estado de conclusão. Fornece helpers de apresentação
  (``cor_prioridade``, ``classe_badge``, ``atrasado``, ``iniciais_responsavel``).

Enums em PT-BR via ``models.TextChoices``. As cores reutilizam os tokens da
seção 8 da SPEC (verde/azul/amarelo/vermelho).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("modulos.kanban.models")

# Cor padrão de uma coluna nova (accent principal da SPEC, seção 8).
COR_COLUNA_PADRAO = "#7c5cff"

# Cores por prioridade (tokens da seção 8) e classe de badge correspondente.
CORES_PRIORIDADE = {
    "baixa": "#34d399",
    "media": "#38bdf8",
    "alta": "#fbbf24",
    "urgente": "#f87171",
}
CLASSES_BADGE_PRIORIDADE = {
    "baixa": "badge--verde",
    "media": "badge--azul",
    "alta": "badge--amarelo",
    "urgente": "badge--vermelho",
}


class Quadro(models.Model):
    """Um quadro (board) de tarefas, composto por colunas."""

    nome = models.CharField(_("nome"), max_length=120)
    descricao = models.TextField(_("descrição"), blank=True, default="")
    arquivado = models.BooleanField(_("arquivado"), default=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quadros_kanban",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("quadro")
        verbose_name_plural = _("quadros")
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return self.nome


class Coluna(models.Model):
    """Uma coluna (raia) de um quadro, com limite de WIP opcional."""

    quadro = models.ForeignKey(
        Quadro,
        on_delete=models.CASCADE,
        related_name="colunas",
        verbose_name=_("quadro"),
    )
    nome = models.CharField(_("nome"), max_length=80)
    ordem = models.PositiveIntegerField(_("ordem"), default=0)
    limite_wip = models.PositiveIntegerField(
        _("limite de WIP"),
        null=True,
        blank=True,
        help_text=_("Máximo de cartões recomendado nesta coluna (opcional)."),
    )
    cor = models.CharField(_("cor"), max_length=7, default=COR_COLUNA_PADRAO)

    class Meta:
        verbose_name = _("coluna")
        verbose_name_plural = _("colunas")
        ordering = ("quadro", "ordem", "id")

    def __str__(self) -> str:
        return f"{self.quadro.nome} · {self.nome}"

    def em_wip(self) -> int:
        """Quantidade atual de cartões na coluna (uso corrente de WIP)."""
        return self.cartoes.count()

    @property
    def estourou_wip(self) -> bool:
        """Indica se o limite de WIP foi ultrapassado (``False`` se não houver limite)."""
        return self.limite_wip is not None and self.em_wip() > self.limite_wip


class Cartao(models.Model):
    """Uma tarefa dentro de uma coluna (o cartão do Kanban)."""

    class Prioridade(models.TextChoices):
        BAIXA = "baixa", _("Baixa")
        MEDIA = "media", _("Média")
        ALTA = "alta", _("Alta")
        URGENTE = "urgente", _("Urgente")

    coluna = models.ForeignKey(
        Coluna,
        on_delete=models.CASCADE,
        related_name="cartoes",
        verbose_name=_("coluna"),
    )
    titulo = models.CharField(_("título"), max_length=160)
    descricao = models.TextField(_("descrição"), blank=True, default="")
    ordem = models.PositiveIntegerField(_("ordem"), default=0)
    prioridade = models.CharField(
        _("prioridade"),
        max_length=10,
        choices=Prioridade.choices,
        default=Prioridade.MEDIA,
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cartoes_kanban",
        verbose_name=_("responsável"),
    )
    prazo = models.DateField(_("prazo"), null=True, blank=True)
    concluido = models.BooleanField(_("concluído"), default=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cartoes_kanban_criados",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("cartão")
        verbose_name_plural = _("cartões")
        ordering = ("coluna", "ordem", "id")

    def __str__(self) -> str:
        return self.titulo

    # -- Helpers de apresentação -------------------------------------------
    def cor_prioridade(self) -> str:
        """Hex da prioridade (tokens da seção 8), com fallback para o roxo."""
        return CORES_PRIORIDADE.get(self.prioridade, COR_COLUNA_PADRAO)

    def classe_badge(self) -> str:
        """Classe de badge do design system correspondente à prioridade."""
        return CLASSES_BADGE_PRIORIDADE.get(self.prioridade, "badge--roxo")

    def atrasado(self) -> bool:
        """Verdadeiro se há prazo vencido e o cartão ainda não foi concluído."""
        if self.concluido or not self.prazo:
            return False
        return self.prazo < timezone.localdate()

    def iniciais_responsavel(self) -> str:
        """Duas letras para o avatar do responsável (ou ``"?"`` se não houver)."""
        usuario = self.responsavel
        if usuario is None:
            return "?"
        base = (getattr(usuario, "nome_completo", "") or "").strip()
        if not base:
            base = (getattr(usuario, "email", "") or "").strip()
        if not base:
            return "?"
        partes = [p for p in base.split() if p]
        if len(partes) >= 2:
            return (partes[0][0] + partes[1][0]).upper()
        return base[:2].upper()

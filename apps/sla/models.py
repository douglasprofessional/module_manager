"""Modelos do módulo de SLA (adendo docs/SPEC_MODULOS.md — MÓDULO 2).

Define dois modelos:

- ``Politica``: contrato de prazos (resposta e resolução, em horas).
- ``Chamado``: um chamado/ticket regido por uma ``Politica``. Ao salvar,
  calcula os prazos absolutos (``prazo_resposta`` e ``prazo_resolucao``) a
  partir da política e de ``aberto_em``. Expõe métodos de situação de SLA
  (``dentro``/``em_risco``/``estourado``/``cumprido``), o percentual de tempo
  consumido, um texto de tempo restante e o mapeamento para as classes
  ``tag-status--*`` do design system.

Todos os métodos de situação são resilientes a ``None`` (prazos ausentes).
Enums em PT-BR via ``models.TextChoices``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("modulos.sla.models")

# Valor exibido quando um campo/texto está vazio.
SEM_VALOR = "—"

# Situações possíveis do SLA (identificadores internos, estáveis).
SIT_DENTRO = "dentro"
SIT_EM_RISCO = "em_risco"
SIT_ESTOURADO = "estourado"
SIT_CUMPRIDO = "cumprido"

# Rótulos PT-BR de cada situação (para exibição em badges).
ROTULOS_SITUACAO = {
    SIT_DENTRO: _("Dentro do prazo"),
    SIT_EM_RISCO: _("Em risco"),
    SIT_ESTOURADO: _("Estourado"),
    SIT_CUMPRIDO: _("Cumprido"),
}

# Mapa situação -> classe do design system (reutiliza as classes tag-status--*).
CLASSES_SITUACAO = {
    SIT_DENTRO: "tag-status--nova",
    SIT_EM_RISCO: "tag-status--pendente",
    SIT_ESTOURADO: "tag-status--erro",
    SIT_CUMPRIDO: "tag-status--qualificada",
}

# Fração restante do prazo abaixo da qual o chamado entra em "em risco" (< 25%).
LIMIAR_RISCO = 0.25


class Politica(models.Model):
    """Contrato de prazos de atendimento (resposta e resolução, em horas)."""

    nome = models.CharField(_("nome"), max_length=120)
    descricao = models.TextField(_("descrição"), blank=True, default="")
    prazo_resposta_horas = models.PositiveIntegerField(
        _("prazo de resposta (horas)"),
        default=4,
    )
    prazo_resolucao_horas = models.PositiveIntegerField(
        _("prazo de resolução (horas)"),
        default=24,
    )
    ativo = models.BooleanField(_("ativo"), default=True)
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("política de SLA")
        verbose_name_plural = _("políticas de SLA")
        ordering = ("nome",)

    def __str__(self) -> str:
        return self.nome


class Chamado(models.Model):
    """Um chamado regido por uma ``Politica`` de SLA."""

    class Prioridade(models.TextChoices):
        BAIXA = "baixa", _("Baixa")
        MEDIA = "media", _("Média")
        ALTA = "alta", _("Alta")
        URGENTE = "urgente", _("Urgente")

    class Status(models.TextChoices):
        ABERTO = "aberto", _("Aberto")
        EM_ANDAMENTO = "em_andamento", _("Em andamento")
        PAUSADO = "pausado", _("Pausado")
        RESOLVIDO = "resolvido", _("Resolvido")
        FECHADO = "fechado", _("Fechado")

    # Status considerados "em aberto" (contam para SLA ativo).
    STATUS_ABERTOS = (Status.ABERTO, Status.EM_ANDAMENTO, Status.PAUSADO)

    titulo = models.CharField(_("título"), max_length=160)
    descricao = models.TextField(_("descrição"), blank=True, default="")
    politica = models.ForeignKey(
        Politica,
        on_delete=models.PROTECT,
        related_name="chamados",
        verbose_name=_("política"),
    )
    prioridade = models.CharField(
        _("prioridade"),
        max_length=20,
        choices=Prioridade.choices,
        default=Prioridade.MEDIA,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.ABERTO,
    )
    solicitante = models.CharField(_("solicitante"), max_length=150, blank=True, default="")
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chamados_sla",
        verbose_name=_("responsável"),
    )

    aberto_em = models.DateTimeField(_("aberto em"), default=timezone.now)
    primeira_resposta_em = models.DateTimeField(
        _("primeira resposta em"),
        null=True,
        blank=True,
    )
    resolvido_em = models.DateTimeField(_("resolvido em"), null=True, blank=True)

    prazo_resposta = models.DateTimeField(_("prazo de resposta"), null=True, blank=True)
    prazo_resolucao = models.DateTimeField(_("prazo de resolução"), null=True, blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chamados_sla_criados",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("chamado")
        verbose_name_plural = _("chamados")
        ordering = ("-aberto_em",)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["-aberto_em"]),
        ]

    def __str__(self) -> str:
        return self.titulo

    # -- Persistência -------------------------------------------------------
    def save(self, *args, **kwargs) -> None:
        """Calcula os prazos absolutos a partir da política e de ``aberto_em``.

        Só preenche ``prazo_resposta``/``prazo_resolucao`` quando ainda vazios,
        preservando ajustes manuais e evitando recálculo a cada gravação.
        """
        if self.aberto_em is not None and self.politica_id:
            try:
                politica = self.politica
                if self.prazo_resposta is None and politica is not None:
                    self.prazo_resposta = self.aberto_em + timedelta(
                        hours=politica.prazo_resposta_horas
                    )
                if self.prazo_resolucao is None and politica is not None:
                    self.prazo_resolucao = self.aberto_em + timedelta(
                        hours=politica.prazo_resolucao_horas
                    )
            except Exception:  # pragma: no cover - nunca impedir a gravação
                logger.exception("Falha ao calcular prazos do chamado '%s'.", self.titulo)
        super().save(*args, **kwargs)

    # -- Situação de SLA (resilientes a None) -------------------------------
    def situacao_resolucao(self) -> str:
        """Situação do SLA de resolução: dentro/em_risco/estourado/cumprido."""
        if self.resolvido_em is not None:
            if self.prazo_resolucao is None:
                return SIT_CUMPRIDO
            return SIT_CUMPRIDO if self.resolvido_em <= self.prazo_resolucao else SIT_ESTOURADO
        return self._situacao_aberto(self.prazo_resolucao)

    def situacao_resposta(self) -> str:
        """Situação do SLA de resposta: dentro/em_risco/estourado/cumprido."""
        if self.primeira_resposta_em is not None:
            if self.prazo_resposta is None:
                return SIT_CUMPRIDO
            return (
                SIT_CUMPRIDO
                if self.primeira_resposta_em <= self.prazo_resposta
                else SIT_ESTOURADO
            )
        return self._situacao_aberto(self.prazo_resposta)

    def _situacao_aberto(self, prazo: datetime | None) -> str:
        """Situação de um marco ainda não cumprido, dado seu ``prazo``.

        Sem prazo definido, assume ``dentro`` (nada a violar). Já vencido é
        ``estourado``; faltando menos de ``LIMIAR_RISCO`` do tempo total é
        ``em_risco``; caso contrário, ``dentro``.
        """
        if prazo is None:
            return SIT_DENTRO
        agora = timezone.now()
        if agora > prazo:
            return SIT_ESTOURADO
        inicio = self.aberto_em
        if inicio is None:
            return SIT_DENTRO
        total = (prazo - inicio).total_seconds()
        if total <= 0:
            return SIT_DENTRO
        restante = (prazo - agora).total_seconds()
        if restante / total < LIMIAR_RISCO:
            return SIT_EM_RISCO
        return SIT_DENTRO

    def percentual_resolucao(self) -> int:
        """Percentual (0..100) do prazo de resolução já consumido.

        Usa ``resolvido_em`` como fim quando o chamado já foi resolvido; caso
        contrário, o instante atual. Resiliente a prazos/datas ausentes.
        """
        inicio = self.aberto_em
        prazo = self.prazo_resolucao
        if inicio is None or prazo is None:
            return 0
        total = (prazo - inicio).total_seconds()
        if total <= 0:
            return 100
        fim = self.resolvido_em or timezone.now()
        consumido = (fim - inicio).total_seconds()
        pct = consumido / total * 100
        return max(0, min(100, round(pct)))

    def tempo_restante_texto(self) -> str:
        """Texto do tempo restante/atraso do prazo de resolução.

        Ex.: ``"faltam 3 h"``, ``"atrasado 2 h"``, ``"—"``. Para chamados já
        resolvidos ou fechados (sem prazo em aberto), retorna ``"—"``.
        """
        prazo = self.prazo_resolucao
        if prazo is None:
            return SEM_VALOR
        if self.resolvido_em is not None or self.status == self.Status.FECHADO:
            return SEM_VALOR
        segundos = (prazo - timezone.now()).total_seconds()
        return self._formatar_duracao(segundos)

    def _formatar_duracao(self, segundos: float) -> str:
        """Formata segundos restantes (positivo) ou de atraso (negativo)."""
        atrasado = segundos < 0
        horas = int(abs(segundos) // 3600)
        if horas < 1:
            corpo = _("menos de 1 h")
        elif horas < 48:
            corpo = _("%(h)d h") % {"h": horas}
        else:
            corpo = _("%(d)d d") % {"d": horas // 24}
        if atrasado:
            return _("atrasado %(t)s") % {"t": corpo}
        return _("faltam %(t)s") % {"t": corpo}

    # -- Apresentação -------------------------------------------------------
    def classe_situacao(self, situacao: str) -> str:
        """Classe ``tag-status--*`` correspondente à ``situacao`` informada."""
        return CLASSES_SITUACAO.get(situacao, "tag-status--nova")

    def rotulo_situacao(self, situacao: str):
        """Rótulo PT-BR legível da ``situacao`` informada."""
        return ROTULOS_SITUACAO.get(situacao, situacao or SEM_VALOR)

    # Conveniências sem argumentos (chamáveis diretamente nos templates, que não
    # sabem passar parâmetros a métodos). Reaproveitam ``situacao_resolucao``.
    def classe_situacao_resolucao(self) -> str:
        """Classe ``tag-status--*`` da situação de resolução atual."""
        return self.classe_situacao(self.situacao_resolucao())

    def rotulo_situacao_resolucao(self):
        """Rótulo PT-BR da situação de resolução atual."""
        return self.rotulo_situacao(self.situacao_resolucao())

    def classe_badge_prioridade(self) -> str:
        """Classe ``badge--*`` do design system para a prioridade do chamado."""
        return {
            self.Prioridade.BAIXA: "badge--verde",
            self.Prioridade.MEDIA: "badge--azul",
            self.Prioridade.ALTA: "badge--amarelo",
            self.Prioridade.URGENTE: "badge--vermelho",
        }.get(self.prioridade, "badge--roxo")

    def iniciais_responsavel(self) -> str:
        """Até 2 letras para o avatar do responsável (ou ``"—"`` se não houver)."""
        if self.responsavel is None:
            return SEM_VALOR
        base = (
            getattr(self.responsavel, "nome_completo", "")
            or getattr(self.responsavel, "email", "")
            or ""
        ).strip()
        if not base:
            return "?"
        partes = [p for p in base.split() if p]
        if len(partes) >= 2:
            return (partes[0][0] + partes[-1][0]).upper()
        return base[:2].upper()

    def nome_responsavel(self) -> str:
        """Nome exibível do responsável (nome completo, e-mail ou ``"—"``)."""
        if self.responsavel is None:
            return SEM_VALOR
        return (
            getattr(self.responsavel, "nome_completo", "")
            or getattr(self.responsavel, "email", "")
            or SEM_VALOR
        )

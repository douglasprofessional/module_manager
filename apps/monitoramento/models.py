"""Modelos do módulo de Monitoramento de VPSs (adendo 2 — MÓDULO 3).

Define dois modelos:

- ``ServidorVPS``: um servidor/VPS monitorado por SSH. As credenciais (senha,
  chave privada e passphrase) são SEMPRE armazenadas cifradas em repouso
  (campos ``*_criptografada`` + properties que decifram/cifram sob demanda —
  MESMO padrão de ``ConexaoGoogle.chave_api``). Os segredos NUNCA são expostos
  no admin, em serializações, logs ou JSON.
- ``LeituraMetrica``: uma leitura histórica de métricas (CPU/RAM/disco/uptime/
  carga) coletada de um servidor.

Enums em PT-BR via ``models.TextChoices``.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.nucleo import criptografia

logger = logging.getLogger("modulos.monitoramento.models")

# Limiares de uso (%) para a cor das barras/medidores (verde/amarelo/vermelho).
LIMIAR_USO_ATENCAO = 70
LIMIAR_USO_CRITICO = 90

# Paleta dos medidores (tokens da seção 8 da SPEC).
COR_USO_OK = "#34d399"        # verde   (< 70%)
COR_USO_ATENCAO = "#fbbf24"   # amarelo (70..89%)
COR_USO_CRITICO = "#f87171"   # vermelho (>= 90%)
COR_USO_NEUTRO = "#6b7280"    # cinza   (sem dado)

# Mapa status -> classe do design system (reutiliza tag-status--* existentes).
CLASSES_STATUS = {
    "online": "tag-status--qualificada",   # verde
    "offline": "tag-status--erro",         # vermelho
    "erro": "tag-status--erro",            # vermelho
    "desconhecido": "tag-status--descartada",  # cinza neutro
}


class ServidorVPS(models.Model):
    """Um servidor/VPS monitorado via SSH, com credenciais cifradas em repouso."""

    class MetodoAuth(models.TextChoices):
        SENHA = "senha", _("Senha")
        CHAVE = "chave", _("Chave privada")

    class Status(models.TextChoices):
        DESCONHECIDO = "desconhecido", _("Desconhecido")
        ONLINE = "online", _("Online")
        OFFLINE = "offline", _("Offline")
        ERRO = "erro", _("Erro")

    nome = models.CharField(_("nome"), max_length=120)
    host = models.CharField(_("host"), max_length=255, help_text=_("IP ou domínio."))
    porta_ssh = models.PositiveIntegerField(_("porta SSH"), default=22)
    usuario = models.CharField(_("usuário"), max_length=64, default="root")
    metodo_auth = models.CharField(
        _("método de autenticação"),
        max_length=10,
        choices=MetodoAuth.choices,
        default=MetodoAuth.SENHA,
    )

    # Segredos SEMPRE cifrados (Fernet). Nunca expor em texto.
    senha_criptografada = models.TextField(
        _("senha (cifrada)"),
        blank=True,
        default="",
        help_text=_("Token cifrado (Fernet). Nunca armazenar a senha em texto."),
    )
    chave_privada_criptografada = models.TextField(
        _("chave privada (cifrada)"),
        blank=True,
        default="",
        help_text=_("Token cifrado (Fernet). Nunca armazenar a chave em texto."),
    )
    passphrase_criptografada = models.TextField(
        _("passphrase (cifrada)"),
        blank=True,
        default="",
        help_text=_("Token cifrado (Fernet). Nunca armazenar a passphrase em texto."),
    )

    host_key_fingerprint = models.CharField(
        _("fingerprint da host key"),
        max_length=200,
        blank=True,
        default="",
        help_text=_(
            "Fingerprint SHA-256 da host key aprendido na 1ª conexão (TOFU). "
            "Se a host key mudar, a coleta é recusada (possível MITM)."
        ),
    )

    provedor = models.CharField(_("provedor"), max_length=80, blank=True, default="")
    tags = models.CharField(_("tags"), max_length=200, blank=True, default="")
    observacoes = models.TextField(_("observações"), blank=True, default="")
    ativo = models.BooleanField(_("ativo"), default=True)

    ultimo_status = models.CharField(
        _("último status"),
        max_length=15,
        choices=Status.choices,
        default=Status.DESCONHECIDO,
    )
    ultima_coleta_em = models.DateTimeField(_("última coleta em"), null=True, blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vps_monitoradas",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("servidor VPS")
        verbose_name_plural = _("servidores VPS")
        ordering = ("nome",)

    def __str__(self) -> str:
        return f"{self.nome} ({self.host})"

    # -- Segredos cifrados (mesmo padrão de ConexaoGoogle.chave_api) --------
    @property
    def senha(self) -> str:
        """Senha em texto claro, decifrada sob demanda (nunca persistida assim)."""
        return self._decifrar(self.senha_criptografada, "senha")

    @senha.setter
    def senha(self, valor: str | None) -> None:
        """Cifra e persiste a senha; string vazia limpa o campo."""
        self.senha_criptografada = self._cifrar(valor)

    @property
    def chave_privada(self) -> str:
        """Chave privada em texto claro, decifrada sob demanda."""
        return self._decifrar(self.chave_privada_criptografada, "chave_privada")

    @chave_privada.setter
    def chave_privada(self, valor: str | None) -> None:
        """Cifra e persiste a chave privada; string vazia limpa o campo."""
        # Preserva quebras de linha da chave PEM/OpenSSH (não faz strip do miolo).
        texto = valor or ""
        self.chave_privada_criptografada = (
            criptografia.criptografar(texto) if texto.strip() else ""
        )

    @property
    def passphrase(self) -> str:
        """Passphrase em texto claro, decifrada sob demanda."""
        return self._decifrar(self.passphrase_criptografada, "passphrase")

    @passphrase.setter
    def passphrase(self, valor: str | None) -> None:
        """Cifra e persiste a passphrase; string vazia limpa o campo."""
        self.passphrase_criptografada = self._cifrar(valor)

    @property
    def tem_credencial(self) -> bool:
        """Indica se há alguma credencial configurada, sem revelar o valor."""
        return bool(
            self.senha_criptografada
            or self.chave_privada_criptografada
        )

    def _decifrar(self, token: str, rotulo: str) -> str:
        """Decifra um token cifrado; falha não derruba o fluxo (retorna '')."""
        if not token:
            return ""
        try:
            return criptografia.descriptografar(token)
        except Exception:  # token inválido/corrompido não deve derrubar a coleta
            # NUNCA logar o valor: apenas o identificador do servidor e o campo.
            logger.exception(
                "Falha ao descriptografar '%s' do servidor %s.", rotulo, self.pk
            )
            return ""

    @staticmethod
    def _cifrar(valor: str | None) -> str:
        """Cifra ``valor`` preservando o conteúdo EXATO (string vazia limpa o campo).

        Não faz ``strip`` do conteúdo: senhas/passphrases podem conter espaços
        significativos (o form usa ``strip=False``). Apenas decide limpar o campo
        quando o valor é vazio/só-espaços.
        """
        bruto = valor or ""
        return criptografia.criptografar(bruto) if bruto.strip() else ""

    # -- Apresentação -------------------------------------------------------
    def classe_status(self) -> str:
        """Classe ``tag-status--*`` do design system para o status atual."""
        return CLASSES_STATUS.get(self.ultimo_status, "tag-status--descartada")

    def iniciais(self) -> str:
        """Até 2 letras maiúsculas para o avatar do servidor."""
        nome = (self.nome or "").strip()
        if not nome:
            return "?"
        partes = [p for p in nome.split() if p]
        if len(partes) >= 2:
            return (partes[0][0] + partes[1][0]).upper()
        return nome[:2].upper()

    def cor_uso(self, pct) -> str:
        """Cor (#hex) para uma barra de uso: verde<70, amarelo 70-89, vermelho>=90."""
        if pct is None:
            return COR_USO_NEUTRO
        try:
            valor = float(pct)
        except (TypeError, ValueError):
            return COR_USO_NEUTRO
        if valor >= LIMIAR_USO_CRITICO:
            return COR_USO_CRITICO
        if valor >= LIMIAR_USO_ATENCAO:
            return COR_USO_ATENCAO
        return COR_USO_OK


class LeituraMetrica(models.Model):
    """Uma leitura histórica de métricas de um ``ServidorVPS``."""

    servidor = models.ForeignKey(
        ServidorVPS,
        on_delete=models.CASCADE,
        related_name="leituras",
        verbose_name=_("servidor"),
    )
    coletado_em = models.DateTimeField(_("coletado em"), auto_now_add=True, db_index=True)
    online = models.BooleanField(_("online"), default=False)

    cpu_pct = models.FloatField(_("CPU (%)"), null=True, blank=True)
    mem_pct = models.FloatField(_("memória (%)"), null=True, blank=True)
    mem_total_mb = models.IntegerField(_("memória total (MB)"), null=True, blank=True)
    mem_usada_mb = models.IntegerField(_("memória usada (MB)"), null=True, blank=True)
    disco_pct = models.FloatField(_("disco (%)"), null=True, blank=True)
    disco_total_gb = models.FloatField(_("disco total (GB)"), null=True, blank=True)
    disco_usado_gb = models.FloatField(_("disco usado (GB)"), null=True, blank=True)
    uptime_segundos = models.BigIntegerField(_("uptime (segundos)"), null=True, blank=True)
    carga1 = models.FloatField(_("carga 1 min"), null=True, blank=True)
    carga5 = models.FloatField(_("carga 5 min"), null=True, blank=True)
    carga15 = models.FloatField(_("carga 15 min"), null=True, blank=True)
    nucleos = models.IntegerField(_("núcleos"), null=True, blank=True)
    sistema = models.CharField(_("sistema"), max_length=200, blank=True, default="")
    erro = models.TextField(_("erro"), blank=True, default="")

    class Meta:
        verbose_name = _("leitura de métrica")
        verbose_name_plural = _("leituras de métrica")
        ordering = ("-coletado_em",)

    def __str__(self) -> str:
        return f"{self.servidor_id} @ {self.coletado_em:%d/%m/%Y %H:%M}"

    def uptime_texto(self) -> str:
        """Formata ``uptime_segundos`` como ``"Xd Yh"`` (ou ``"—"`` se ausente)."""
        if self.uptime_segundos is None:
            return "—"
        try:
            total = int(self.uptime_segundos)
        except (TypeError, ValueError):
            return "—"
        if total < 0:
            return "—"
        dias = total // 86400
        horas = (total % 86400) // 3600
        if dias > 0:
            return f"{dias}d {horas}h"
        minutos = (total % 3600) // 60
        return f"{horas}h {minutos}min"

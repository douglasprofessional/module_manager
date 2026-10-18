"""Modelos do módulo de Marketing por E-mail (adendo 3 — MÓDULO 5).

Solução AUTOCONTIDA de envio em massa:

- ``ConfiguracaoEnvio``: a "conta de envio" (remetente + SMTP). A senha SMTP é
  SEMPRE armazenada cifrada em repouso (campo ``senha_criptografada`` + property
  ``senha`` que decifra/cifra sob demanda — MESMO padrão de
  ``ConexaoGoogle.chave_api``). A senha NUNCA é exposta em log, admin ou JSON. O
  método ``abrir_conexao()`` devolve uma conexão de e-mail do Django construída a
  partir DESTA configuração (não usa as configs globais ``EMAIL_*``).
- ``Contato``: um destinatário, com token de descadastro grande e aleatório
  (``secrets``) para a página pública de opt-out.
- ``Lista``: um agrupamento de contatos.
- ``Campanha``: um envio em massa (assunto + corpos + configuração + lista).
- ``EnvioEmail``: o log por destinatário (resiliência e contadores).

Enums em PT-BR via ``models.TextChoices``.
"""
from __future__ import annotations

import logging
import secrets
from email.utils import formataddr

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

from apps.nucleo import criptografia

logger = logging.getLogger("modulos.email_marketing.models")

# Timeout (segundos) das conexões SMTP abertas pelo módulo.
TIMEOUT_SMTP = 20

# Tamanho (bytes de entropia) do token de descadastro. ``token_urlsafe(32)``
# gera ~43 caracteres URL-safe: grande o bastante para inviabilizar enumeração.
ENTROPIA_TOKEN = 32

# Mapa status da campanha -> classe do design system (reutiliza tag-status--*).
CLASSES_STATUS = {
    "rascunho": "tag-status--descartada",   # neutro
    "enviando": "tag-status--executando",   # azul (em progresso)
    "enviada": "tag-status--concluida",     # verde
    "parcial": "tag-status--pendente",      # amarelo (atenção)
    "erro": "tag-status--erro",             # vermelho
}


class ConfiguracaoEnvio(models.Model):
    """Conta de envio (remetente + SMTP), com a senha sempre cifrada em repouso."""

    class Tipo(models.TextChoices):
        SMTP = "smtp", _("SMTP")
        CONSOLE = "console", _("Console (teste)")

    nome = models.CharField(_("nome"), max_length=120)
    tipo = models.CharField(
        _("tipo"),
        max_length=10,
        choices=Tipo.choices,
        default=Tipo.CONSOLE,
        help_text=_(
            "Console (teste) imprime o e-mail no log — ideal para testar o envio "
            "em massa localmente sem um SMTP real."
        ),
    )

    email_remetente = models.EmailField(_("e-mail remetente"))
    nome_remetente = models.CharField(_("nome do remetente"), max_length=120, blank=True, default="")
    responder_para = models.EmailField(_("responder para (Reply-To)"), blank=True, default="")

    host = models.CharField(_("host SMTP"), max_length=255, blank=True, default="")
    porta = models.PositiveIntegerField(_("porta"), default=587)
    usuario = models.CharField(_("usuário SMTP"), max_length=255, blank=True, default="")

    # Segredo SEMPRE cifrado (Fernet). Nunca expor em texto.
    senha_criptografada = models.TextField(
        _("senha SMTP (cifrada)"),
        blank=True,
        default="",
        help_text=_("Token cifrado (Fernet). Nunca armazenar a senha em texto."),
    )

    usar_tls = models.BooleanField(_("usar TLS (STARTTLS)"), default=True)
    usar_ssl = models.BooleanField(_("usar SSL"), default=False)
    ativo = models.BooleanField(_("ativa"), default=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="config_envio_email",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("configuração de envio")
        verbose_name_plural = _("configurações de envio")
        ordering = ("nome",)

    def __str__(self) -> str:
        return f"{self.nome} <{self.email_remetente}>"

    # -- Segredo cifrado (mesmo padrão de ConexaoGoogle.chave_api) -----------
    @property
    def senha(self) -> str:
        """Senha SMTP em texto claro, decifrada sob demanda (nunca persistida assim)."""
        if not self.senha_criptografada:
            return ""
        try:
            return criptografia.descriptografar(self.senha_criptografada)
        except Exception:  # token inválido/corrompido não deve derrubar o envio
            # NUNCA logar o valor: apenas o identificador da configuração.
            logger.exception("Falha ao descriptografar a senha SMTP da configuração %s.", self.pk)
            return ""

    @senha.setter
    def senha(self, valor: str | None) -> None:
        """Cifra e persiste a senha preservando o conteúdo EXATO.

        Não faz ``strip`` do conteúdo (senhas podem conter espaços significativos;
        o form usa ``strip=False``). Apenas decide LIMPAR o campo quando o valor é
        vazio/só-espaços.
        """
        bruto = valor or ""
        self.senha_criptografada = criptografia.criptografar(bruto) if bruto.strip() else ""

    @property
    def tem_senha(self) -> bool:
        """Indica se há uma senha SMTP configurada, sem revelá-la."""
        return bool(self.senha_criptografada)

    # -- Envio (autocontido) ------------------------------------------------
    def remetente_formatado(self) -> str:
        """Retorna o cabeçalho ``De`` no formato ``"Nome <email>"`` (ou só o e-mail)."""
        return formataddr((self.nome_remetente or "", self.email_remetente))

    def abrir_conexao(self):
        """Abre uma conexão de e-mail do Django a partir DESTA configuração.

        Não usa as configs globais ``EMAIL_*`` do Django — a solução é autocontida:

        - tipo CONSOLE: ``console.EmailBackend`` (imprime o e-mail no stdout/log,
          ideal para testar o envio em massa localmente sem um SMTP real);
        - tipo SMTP: ``smtp.EmailBackend`` com host/porta/usuário/senha desta
          configuração (a senha é decifrada apenas em memória, nunca logada).
        """
        from django.core.mail import get_connection

        if self.tipo == self.Tipo.CONSOLE:
            return get_connection("django.core.mail.backends.console.EmailBackend")
        return get_connection(
            "django.core.mail.backends.smtp.EmailBackend",
            host=self.host,
            port=self.porta,
            username=self.usuario,
            password=self.senha,  # decifrada só aqui, em memória
            use_tls=self.usar_tls,
            use_ssl=self.usar_ssl,
            timeout=TIMEOUT_SMTP,
        )


class TemplateEmail(models.Model):
    """Modelo (template) de e-mail HTML reutilizável e 100% editável.

    A biblioteca vem com 10 layouts responsivos prontos (semeados de forma
    idempotente por ``seed_templates_email``). Ao criar uma campanha, o admin
    pode partir de um template: o ``corpo_html``/``corpo_texto`` são COPIADOS
    para a campanha e podem ser editados livremente sem afetar o template.
    """

    class Categoria(models.TextChoices):
        BOAS_VINDAS = "boas_vindas", _("Boas-vindas")
        NEWSLETTER = "newsletter", _("Newsletter")
        PROMOCAO = "promocao", _("Promoção")
        ANUNCIO = "anuncio", _("Anúncio")
        EVENTO = "evento", _("Evento")
        FOLLOWUP = "followup", _("Follow-up")
        REENGAJAMENTO = "reengajamento", _("Reengajamento")
        TRANSACIONAL = "transacional", _("Transacional")
        SIMPLES = "simples", _("Texto simples")
        CUPOM = "cupom", _("Cupom / Oferta")

    nome = models.CharField(_("nome"), max_length=120)
    descricao = models.CharField(_("descrição"), max_length=240, blank=True, default="")
    categoria = models.CharField(
        _("categoria"),
        max_length=20,
        choices=Categoria.choices,
        default=Categoria.SIMPLES,
    )
    corpo_html = models.TextField(_("corpo (HTML)"))
    corpo_texto = models.TextField(
        _("corpo (texto puro)"),
        blank=True,
        default="",
        help_text=_("Alternativa em texto puro. Se vazio, é derivado do HTML."),
    )
    # ``builtin`` marca os 10 modelos oficiais (semeados). Continuam editáveis.
    builtin = models.BooleanField(_("modelo padrão do sistema"), default=False)
    ativo = models.BooleanField(_("ativo"), default=True)
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("modelo de e-mail")
        verbose_name_plural = _("modelos de e-mail")
        ordering = ("categoria", "nome")

    def __str__(self) -> str:
        return self.nome

    def corpo_texto_efetivo(self) -> str:
        """Corpo em texto puro informado, ou derivado do HTML via ``strip_tags``."""
        return self.corpo_texto or strip_tags(self.corpo_html)


class Contato(models.Model):
    """Um destinatário de campanhas, com token público de descadastro."""

    email = models.EmailField(_("e-mail"), unique=True)
    nome = models.CharField(_("nome"), max_length=150, blank=True, default="")
    empresa = models.CharField(_("empresa"), max_length=150, blank=True, default="")
    tags = models.CharField(_("tags"), max_length=200, blank=True, default="")

    inscrito = models.BooleanField(_("inscrito"), default=True)
    descadastrado_em = models.DateTimeField(_("descadastrado em"), null=True, blank=True)
    token_descadastro = models.CharField(
        _("token de descadastro"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("Token grande e aleatório usado no link público de opt-out."),
    )

    origem = models.CharField(_("origem"), max_length=80, blank=True, default="")
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("contato")
        verbose_name_plural = _("contatos")
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs) -> None:
        """Gera um ``token_descadastro`` grande e aleatório na primeira gravação."""
        if not self.token_descadastro:
            self.token_descadastro = secrets.token_urlsafe(ENTROPIA_TOKEN)
        super().save(*args, **kwargs)

    # -- Regras de domínio --------------------------------------------------
    def descadastrar(self) -> None:
        """Marca o contato como descadastrado (idempotente).

        Só grava se houver mudança; a data de descadastro é preservada em
        chamadas repetidas.
        """
        if not self.inscrito and self.descadastrado_em is not None:
            return
        self.inscrito = False
        if self.descadastrado_em is None:
            self.descadastrado_em = timezone.now()
        self.save(update_fields=["inscrito", "descadastrado_em"])

    # -- Apresentação / personalização --------------------------------------
    def primeiro_nome(self) -> str:
        """Primeiro nome para saudação; se não houver nome, usa o início do e-mail."""
        nome = (self.nome or "").strip()
        if nome:
            return nome.split()[0]
        return (self.email or "").split("@")[0]

    def iniciais(self) -> str:
        """Até 2 letras maiúsculas para o avatar do contato."""
        base = (self.nome or "").strip() or (self.email or "")
        partes = [p for p in base.split() if p]
        if len(partes) >= 2:
            return (partes[0][0] + partes[1][0]).upper()
        return base[:2].upper() if base else "?"


class Lista(models.Model):
    """Um agrupamento de contatos para segmentar campanhas."""

    nome = models.CharField(_("nome"), max_length=120)
    descricao = models.TextField(_("descrição"), blank=True, default="")
    contatos = models.ManyToManyField(
        Contato,
        blank=True,
        related_name="listas",
        verbose_name=_("contatos"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("lista")
        verbose_name_plural = _("listas")
        ordering = ("nome",)

    def __str__(self) -> str:
        return self.nome

    def destinatarios(self):
        """Contatos desta lista que ainda estão inscritos (queryset)."""
        return self.contatos.filter(inscrito=True)


class Campanha(models.Model):
    """Um envio em massa: assunto + corpos + configuração de envio + lista."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        ENVIANDO = "enviando", _("Enviando")
        ENVIADA = "enviada", _("Enviada")
        PARCIAL = "parcial", _("Parcial")
        ERRO = "erro", _("Erro")

    nome = models.CharField(_("nome"), max_length=160)
    assunto = models.CharField(_("assunto"), max_length=200)
    corpo_html = models.TextField(_("corpo (HTML)"))
    corpo_texto = models.TextField(
        _("corpo (texto puro)"),
        blank=True,
        default="",
        help_text=_("Alternativa em texto puro. Se vazio, é derivado do HTML."),
    )

    configuracao = models.ForeignKey(
        ConfiguracaoEnvio,
        on_delete=models.PROTECT,
        related_name="campanhas",
        verbose_name=_("configuração de envio"),
    )
    lista = models.ForeignKey(
        Lista,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campanhas",
        verbose_name=_("lista"),
        help_text=_("Vazio = todos os contatos inscritos."),
    )

    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.RASCUNHO,
    )
    total_destinatarios = models.PositiveIntegerField(_("total de destinatários"), default=0)
    total_enviados = models.PositiveIntegerField(_("total enviados"), default=0)
    total_falhas = models.PositiveIntegerField(_("total de falhas"), default=0)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campanhas_email",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    enviada_em = models.DateTimeField(_("enviada em"), null=True, blank=True)

    class Meta:
        verbose_name = _("campanha")
        verbose_name_plural = _("campanhas")
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return self.nome

    # -- Regras de domínio --------------------------------------------------
    def destinatarios(self):
        """Retorna os destinatários inscritos: da lista, ou TODOS se não houver lista."""
        if self.lista_id:
            return self.lista.destinatarios()
        return Contato.objects.filter(inscrito=True)

    def pode_enviar(self) -> bool:
        """Só é possível enviar quando em rascunho, com erro ou parcialmente enviada."""
        return self.status in (self.Status.RASCUNHO, self.Status.ERRO, self.Status.PARCIAL)

    def corpo_texto_efetivo(self) -> str:
        """Corpo em texto puro informado, ou derivado do HTML via ``strip_tags``."""
        return self.corpo_texto or strip_tags(self.corpo_html)

    def classe_status(self) -> str:
        """Classe ``tag-status--*`` do design system para o status atual."""
        return CLASSES_STATUS.get(self.status, "tag-status--descartada")


class EnvioEmail(models.Model):
    """Log de envio por destinatário (resiliência e contadores da campanha)."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", _("Pendente")
        ENVIADO = "enviado", _("Enviado")
        FALHA = "falha", _("Falha")

    campanha = models.ForeignKey(
        Campanha,
        on_delete=models.CASCADE,
        related_name="envios",
        verbose_name=_("campanha"),
    )
    contato = models.ForeignKey(
        Contato,
        on_delete=models.SET_NULL,
        null=True,
        related_name="envios",
        verbose_name=_("contato"),
    )
    email = models.CharField(_("e-mail (snapshot)"), max_length=254)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.PENDENTE,
    )
    erro = models.CharField(_("erro"), max_length=255, blank=True, default="")
    enviado_em = models.DateTimeField(_("enviado em"), null=True, blank=True)
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("envio de e-mail")
        verbose_name_plural = _("envios de e-mail")
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return f"{self.email} — {self.get_status_display()}"

    def classe_status(self) -> str:
        """Classe ``tag-status--*`` do design system para o status do envio."""
        if self.status == self.Status.ENVIADO:
            return "tag-status--concluida"
        if self.status == self.Status.FALHA:
            return "tag-status--erro"
        return "tag-status--pendente"

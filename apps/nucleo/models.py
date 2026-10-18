"""Modelos do núcleo.

Contém:

- ``RegistroAuditoria``: trilha de auditoria mínima e imutável (quem, o quê,
  sobre qual objeto, de qual IP e quando). Ordenado do mais recente ao antigo.
- ``ConfiguracaoSistema``: singleton de marca branca (nome do sistema, logo e
  tema padrão). Lido em todas as páginas via context processor (com cache).
- ``ModuloEstado``: liga/desliga de cada módulo plugável. Todos começam
  DESLIGADOS (padrão do pedido): o admin habilita no painel de Configurações.
"""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.nucleo.textos import texto
from apps.nucleo.validators import validar_logo


class RegistroAuditoria(models.Model):
    """Uma entrada de auditoria (append-only).

    O ``usuario`` é opcional (``null``) para preservar o histórico mesmo que a
    conta seja removida (``on_delete=SET_NULL``). Nenhum campo deve conter
    segredos em texto puro.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
        verbose_name="usuário",
    )
    acao = models.CharField("ação", max_length=150)
    objeto_repr = models.CharField(
        "objeto",
        max_length=255,
        blank=True,
        help_text="Representação textual do objeto afetado.",
    )
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    quando = models.DateTimeField("quando", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-quando"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"

    def __str__(self) -> str:
        usuario = self.usuario or "sistema"
        return f"{usuario} — {self.acao}"


# ---------------------------------------------------------------------------
# Configuração do sistema (marca branca) — singleton
# ---------------------------------------------------------------------------
CHAVE_CACHE_CONFIG = "nucleo:configuracao_sistema"


class Tema(models.TextChoices):
    """Temas visuais suportados (padrão: claro)."""

    CLARO = "claro", _("Claro")
    ESCURO = "escuro", _("Escuro")


class ConfiguracaoSistema(models.Model):
    """Configurações globais de marca branca (uma única linha, ``pk=1``).

    Use ``ConfiguracaoSistema.obter()`` (com cache) para ler em qualquer lugar.
    """

    nome_sistema = models.CharField(
        _("nome do sistema"),
        max_length=80,
        default=texto("geral.nome_padrao"),
        help_text=_("Exibido na barra superior, na aba do navegador e nos e-mails."),
    )
    logo = models.FileField(
        _("logo"),
        upload_to="marca/",
        blank=True,
        null=True,
        validators=[validar_logo],
        help_text=_("PNG, JPG, WEBP ou SVG. Até 2 MB."),
    )
    tema_padrao = models.CharField(
        _("tema padrão"),
        max_length=10,
        choices=Tema.choices,
        default=Tema.CLARO,
        help_text=_("Tema aplicado a quem ainda não escolheu um."),
    )
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("configuração do sistema")
        verbose_name_plural = _("configuração do sistema")

    def __str__(self) -> str:
        return self.nome_sistema

    def save(self, *args, **kwargs):
        """Força o singleton (``pk=1``) e invalida o cache."""
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CHAVE_CACHE_CONFIG)

    def delete(self, *args, **kwargs):  # pragma: no cover - proteção do singleton
        """Não permite excluir o singleton; apenas limpa o cache."""
        cache.delete(CHAVE_CACHE_CONFIG)

    @classmethod
    def obter(cls) -> "ConfiguracaoSistema":
        """Retorna o singleton (criando com padrões se necessário), com cache.

        Resiliente: se a tabela ainda não existe (durante o primeiro migrate),
        devolve uma instância em memória com os padrões, sem tocar no banco.
        """
        config = cache.get(CHAVE_CACHE_CONFIG)
        if config is not None:
            return config
        try:
            config, _criado = cls.objects.get_or_create(pk=1)
        except Exception:
            return cls(pk=1)
        cache.set(CHAVE_CACHE_CONFIG, config, 300)
        return config


# ---------------------------------------------------------------------------
# Estado (liga/desliga) por módulo plugável
# ---------------------------------------------------------------------------
CHAVE_CACHE_MODULOS = "nucleo:modulos_habilitados"


class ModuloEstado(models.Model):
    """Persistência do liga/desliga de um módulo, identificado pelo ``slug``.

    Ausência de linha == módulo DESLIGADO (padrão do pedido: tudo desligado).
    """

    slug = models.SlugField(_("módulo"), max_length=50, unique=True)
    habilitado = models.BooleanField(_("habilitado"), default=False)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("estado de módulo")
        verbose_name_plural = _("estados de módulos")
        ordering = ("slug",)

    def __str__(self) -> str:
        return f"{self.slug}: {'on' if self.habilitado else 'off'}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(CHAVE_CACHE_MODULOS)

    @classmethod
    def slugs_habilitados(cls) -> set[str]:
        """Conjunto de slugs habilitados (com cache; resiliente a tabela ausente)."""
        slugs = cache.get(CHAVE_CACHE_MODULOS)
        if slugs is not None:
            return slugs
        try:
            slugs = set(
                cls.objects.filter(habilitado=True).values_list("slug", flat=True)
            )
        except Exception:
            return set()
        cache.set(CHAVE_CACHE_MODULOS, slugs, 300)
        return slugs

    @classmethod
    def definir(cls, slug: str, habilitado: bool) -> "ModuloEstado":
        """Cria/atualiza o estado de um módulo e invalida o cache."""
        estado, _criado = cls.objects.update_or_create(
            slug=slug, defaults={"habilitado": habilitado}
        )
        cache.delete(CHAVE_CACHE_MODULOS)
        return estado

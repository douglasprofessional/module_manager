"""Modelos do módulo de prospecção (seção 11 da SPEC).

Define quatro modelos:

- ``ConexaoGoogle``: credencial da API do Google. A chave é sempre armazenada
  cifrada (property ``chave_api`` decifra sob demanda; o setter cifra). Nunca
  expor a chave em texto no admin ou em serializações.
- ``ConfiguracaoProspeccao``: singleton (``pk=1``) do Painel do módulo — chave
  da Google Places API (New) colada no painel, chave/modelo da IA generativa e
  os limites do motor de análise. Segredos sempre cifrados.
- ``Busca``: uma execução de prospecção (termo + localização + raio).
- ``Empresa``: o lead encontrado, com flags de problemas, scores e as métricas
  da Google Places API (nota, avaliações, fotos, horário, situação e última
  atividade). Fornece ``linha_dashboard()`` (dict ``EmpresaLinha`` da seção 7)
  e ``rotulos_problemas()``.

Os rótulos exibidos vêm de ``apps/nucleo/textos.py`` (fonte única de textos).
Enums em PT-BR via ``models.TextChoices``.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.nucleo import criptografia
from apps.nucleo.textos import texto
from apps.prospeccao.services.analise_places import (
    HORARIO_AUSENTE,
    HORARIO_INCOMPLETO,
    LIMIAR_AVALIACOES_PADRAO,
    LIMIAR_FOTOS_PADRAO,
    LIMIAR_MESES_PADRAO,
    LIMIAR_NOTA_PADRAO,
    STATUS_FECHADA_PERMANENTEMENTE,
    dias_por_meses,
)

logger = logging.getLogger("modulos.prospeccao.models")

# Valor exibido quando um campo está vazio (contrato da tabela do dashboard).
SEM_VALOR = texto("geral.sem_valor")

# Limiares para derivar problemas a partir dos scores (0..100).
LIMIAR_SEO = 50
LIMIAR_PERFORMANCE = 50

# Modelo padrão da IA generativa (Claude) usado nos diagnósticos em texto.
MODELO_IA_PADRAO = "claude-opus-5-5"

# Catálogo de problemas: slug -> (cor do badge, cor da fatia no donut).
# A ordem define a ordem de exibição (badges, filtros e donut). Os rótulos
# ficam em ``textos.py`` (chave ``prospeccao.problemas.<slug>``).
PROBLEMAS: dict[str, tuple[str, str]] = {
    "fechada": ("vermelho", "#ef4444"),
    "sem_site": ("vermelho", "#f87171"),
    "site_desatualizado": ("amarelo", "#fbbf24"),
    "apenas_instagram": ("azul", "#38bdf8"),
    "seo_fraco": ("roxo", "#7c5cff"),
    "performance_baixa": ("amarelo", "#9b7dff"),
    "sem_ssl": ("vermelho", "#f5e6c8"),
    "hospedagem_sem_site": ("roxo", "#34d399"),
    "nota_baixa": ("vermelho", "#fb7185"),
    "poucas_avaliacoes": ("amarelo", "#f59e0b"),
    "sem_horario": ("amarelo", "#fcd34d"),
    "horario_incompleto": ("amarelo", "#fde68a"),
    "poucas_fotos": ("azul", "#60a5fa"),
    "perfil_desatualizado": ("roxo", "#a78bfa"),
}

# Problemas derivados exclusivamente das métricas da Google Places API.
PROBLEMAS_GOOGLE = (
    "nota_baixa",
    "sem_site",
    "poucas_avaliacoes",
    "sem_horario",
    "horario_incompleto",
    "fechada",
    "poucas_fotos",
    "perfil_desatualizado",
)


def rotulo_problema(slug: str) -> str:
    """Rótulo exibido de um problema (fonte: ``textos.py``)."""
    return texto(f"prospeccao.problemas.{slug}")


# Rótulos canônicos (mantidos por compatibilidade com o restante do código).
PROBLEMA_SEM_SITE = rotulo_problema("sem_site")
PROBLEMA_SITE_DESATUALIZADO = rotulo_problema("site_desatualizado")
PROBLEMA_APENAS_INSTAGRAM = rotulo_problema("apenas_instagram")
PROBLEMA_SEO_FRACO = rotulo_problema("seo_fraco")
PROBLEMA_PERFORMANCE_BAIXA = rotulo_problema("performance_baixa")
PROBLEMA_SEM_SSL = rotulo_problema("sem_ssl")
PROBLEMA_HOSPEDAGEM_SEM_SITE = rotulo_problema("hospedagem_sem_site")

# Paleta determinística para o avatar da empresa (tokens da seção 8).
CORES_AVATAR = ("#7c5cff", "#34d399", "#38bdf8", "#fbbf24", "#f87171", "#9b7dff")

CHAVE_CACHE_CONFIG = "prospeccao:configuracao"


class ConexaoGoogle(models.Model):
    """Credencial da API do Google, com a chave sempre cifrada em repouso."""

    nome = models.CharField(_("nome"), max_length=120)
    chave_api_criptografada = models.TextField(
        _("chave da API (cifrada)"),
        blank=True,
        default="",
        help_text=_("Token cifrado (Fernet). Nunca armazenar a chave em texto."),
    )
    ativo = models.BooleanField(_("ativo"), default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conexoes_google",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("conexão Google")
        verbose_name_plural = _("conexões Google")
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return self.nome

    @property
    def chave_api(self) -> str:
        """Chave em texto claro, decifrada sob demanda (nunca persistida assim)."""
        if not self.chave_api_criptografada:
            return ""
        try:
            return criptografia.descriptografar(self.chave_api_criptografada)
        except Exception:  # chave inválida/corrompida não deve derrubar o fluxo
            logger.exception("Falha ao descriptografar a chave da conexão %s.", self.pk)
            return ""

    @chave_api.setter
    def chave_api(self, valor: str | None) -> None:
        """Cifra e persiste a chave; string vazia limpa o campo."""
        valor = (valor or "").strip()
        self.chave_api_criptografada = criptografia.criptografar(valor) if valor else ""

    @property
    def tem_chave(self) -> bool:
        """Indica se há uma chave configurada, sem revelá-la."""
        return bool(self.chave_api_criptografada)


def _decifrar(token: str, contexto: str) -> str:
    """Decifra um segredo salvo; falha vira string vazia (sem derrubar o fluxo)."""
    if not token:
        return ""
    try:
        return criptografia.descriptografar(token)
    except Exception:
        logger.exception("Falha ao descriptografar %s.", contexto)
        return ""


class ConfiguracaoProspeccao(models.Model):
    """Configuração do Painel do módulo (uma única linha, ``pk=1``).

    Guarda a chave da Google Places API (New) colada no painel, a chave e o
    modelo da IA generativa (Claude) e os limites do motor de análise. Use
    ``ConfiguracaoProspeccao.obter()`` (com cache) para ler em qualquer lugar.
    """

    chave_google_criptografada = models.TextField(
        _("chave da Google Places API (cifrada)"), blank=True, default=""
    )
    ia_chave_criptografada = models.TextField(_("chave da API de IA (cifrada)"), blank=True, default="")
    ia_modelo = models.CharField(_("modelo de IA"), max_length=80, default=MODELO_IA_PADRAO)
    ia_ativa = models.BooleanField(_("IA generativa ativa"), default=True)
    limiar_nota = models.FloatField(
        _("nota mínima"),
        default=LIMIAR_NOTA_PADRAO,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
    )
    limiar_avaliacoes = models.PositiveIntegerField(
        _("mínimo de avaliações"), default=LIMIAR_AVALIACOES_PADRAO
    )
    limiar_fotos = models.PositiveSmallIntegerField(
        _("mínimo de fotos"),
        default=LIMIAR_FOTOS_PADRAO,
        validators=[MaxValueValidator(10)],
    )
    limiar_meses = models.PositiveSmallIntegerField(
        _("meses sem atualização"),
        default=LIMIAR_MESES_PADRAO,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("configuração da prospecção")
        verbose_name_plural = _("configuração da prospecção")

    def __str__(self) -> str:
        return str(self._meta.verbose_name)

    def save(self, *args, **kwargs):
        """Força o singleton (``pk=1``) e invalida o cache."""
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CHAVE_CACHE_CONFIG)

    def delete(self, *args, **kwargs):  # pragma: no cover - proteção do singleton
        """Não exclui o singleton; apenas limpa o cache."""
        cache.delete(CHAVE_CACHE_CONFIG)

    @classmethod
    def obter(cls) -> "ConfiguracaoProspeccao":
        """Retorna o singleton (criando com padrões se preciso), com cache.

        Resiliente: se a tabela ainda não existe (primeiro migrate), devolve
        uma instância em memória com os padrões, sem tocar no banco.
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

    # -- Segredos (sempre cifrados em repouso) -----------------------------
    @property
    def chave_google(self) -> str:
        return _decifrar(self.chave_google_criptografada, "a chave do Google")

    @chave_google.setter
    def chave_google(self, valor: str | None) -> None:
        valor = (valor or "").strip()
        self.chave_google_criptografada = criptografia.criptografar(valor) if valor else ""

    @property
    def tem_chave_google(self) -> bool:
        return bool(self.chave_google_criptografada)

    @property
    def ia_chave(self) -> str:
        return _decifrar(self.ia_chave_criptografada, "a chave da IA")

    @ia_chave.setter
    def ia_chave(self, valor: str | None) -> None:
        valor = (valor or "").strip()
        self.ia_chave_criptografada = criptografia.criptografar(valor) if valor else ""

    @property
    def tem_ia_chave(self) -> bool:
        return bool(self.ia_chave_criptografada)

    @property
    def ia_disponivel(self) -> bool:
        """IA generativa pronta para uso (ativa e com chave)."""
        return bool(self.ia_ativa and self.ia_chave_criptografada)

    def data_limite_atualizacao(self):
        """Data antes da qual o perfil é considerado desatualizado."""
        return timezone.localdate() - timedelta(days=dias_por_meses(self.limiar_meses))


def filtros_problema(config: ConfiguracaoProspeccao | None = None) -> dict[str, Q]:
    """Expressões ORM de cada problema (mesmas regras de ``Empresa.problemas_slugs``)."""
    config = config or ConfiguracaoProspeccao.obter()
    analisada = Q(analisado_places_em__isnull=False)
    return {
        "fechada": Q(status_google=STATUS_FECHADA_PERMANENTEMENTE),
        "sem_site": Q(tem_site=False),
        "site_desatualizado": Q(site_desatualizado=True),
        "apenas_instagram": Q(apenas_instagram=True),
        "seo_fraco": Q(score_seo__isnull=False, score_seo__lt=LIMIAR_SEO),
        "performance_baixa": Q(
            score_performance__isnull=False, score_performance__lt=LIMIAR_PERFORMANCE
        ),
        "sem_ssl": Q(tem_ssl=False),
        "hospedagem_sem_site": Q(hospedagem_sem_site=True),
        "nota_baixa": Q(nota_google__isnull=False, nota_google__lt=config.limiar_nota),
        "poucas_avaliacoes": analisada
        & Q(total_avaliacoes__isnull=False, total_avaliacoes__lt=config.limiar_avaliacoes),
        "sem_horario": Q(situacao_horario=HORARIO_AUSENTE),
        "horario_incompleto": Q(situacao_horario=HORARIO_INCOMPLETO),
        "poucas_fotos": analisada
        & Q(total_fotos__isnull=False, total_fotos__lt=config.limiar_fotos),
        "perfil_desatualizado": analisada
        & (
            Q(ultima_atividade_perfil__isnull=True)
            | Q(ultima_atividade_perfil__lt=config.data_limite_atualizacao())
        ),
    }


class Busca(models.Model):
    """Uma execução de prospecção (termo + localização + raio)."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", _("Pendente")
        EXECUTANDO = "executando", _("Executando")
        CONCLUIDA = "concluida", _("Concluída")
        ERRO = "erro", _("Erro")

    # Opcional: sem conexão, a busca usa a chave salva no Painel do módulo.
    conexao = models.ForeignKey(
        ConexaoGoogle,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="buscas",
        verbose_name=_("conexão"),
    )
    termo = models.CharField(_("termo"), max_length=200)
    localizacao = models.CharField(_("localização"), max_length=200)
    raio_metros = models.PositiveIntegerField(_("raio (metros)"), default=5000)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )
    total_resultados = models.PositiveIntegerField(_("total de resultados"), default=0)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buscas",
        verbose_name=_("criado por"),
    )
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("busca")
        verbose_name_plural = _("buscas")
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return f"{self.termo} — {self.localizacao}"


class Empresa(models.Model):
    """Lead encontrado e analisado, com flags de problemas e scores."""

    class Status(models.TextChoices):
        NOVA = "nova", _("Nova")
        QUALIFICADA = "qualificada", _("Qualificada")
        CONTATADA = "contatada", _("Contatada")
        DESCARTADA = "descartada", _("Descartada")

    busca = models.ForeignKey(
        Busca,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="empresas",
        verbose_name=_("busca"),
    )
    place_id = models.CharField(
        _("place_id"),
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    nome = models.CharField(_("nome"), max_length=255)
    categoria = models.CharField(_("categoria"), max_length=150, blank=True, default="")
    endereco = models.CharField(_("endereço"), max_length=255, blank=True, default="")
    telefone = models.CharField(_("telefone"), max_length=50, blank=True, default="")
    whatsapp = models.CharField(_("whatsapp"), max_length=50, blank=True, default="")
    email = models.EmailField(_("e-mail"), blank=True, default="")
    instagram = models.CharField(_("instagram"), max_length=120, blank=True, default="")
    website = models.URLField(_("website"), max_length=300, blank=True, default="")
    dominio = models.CharField(_("domínio"), max_length=255, blank=True, default="")

    tem_site = models.BooleanField(_("tem site"), default=False)
    site_desatualizado = models.BooleanField(_("site desatualizado"), default=False)
    apenas_instagram = models.BooleanField(_("apenas Instagram"), default=False)
    tem_ssl = models.BooleanField(_("tem SSL"), null=True, blank=True)
    hospedagem_sem_site = models.BooleanField(_("hospedagem sem site"), default=False)

    score_seo = models.PositiveSmallIntegerField(
        _("score de SEO"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
    )
    score_performance = models.PositiveSmallIntegerField(
        _("score de performance"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
    )

    data_fundacao = models.DateField(_("data de fundação"), null=True, blank=True)
    tempo_mercado_texto = models.CharField(
        _("tempo de mercado"),
        max_length=100,
        blank=True,
        default="",
    )
    responsavel = models.CharField(_("responsável"), max_length=150, blank=True, default="")
    cargo_responsavel = models.CharField(
        _("cargo do responsável"),
        max_length=100,
        blank=True,
        default="",
    )

    latitude = models.FloatField(_("latitude"), null=True, blank=True)
    longitude = models.FloatField(_("longitude"), null=True, blank=True)

    # -- Métricas da Google Places API (New) -------------------------------
    nota_google = models.FloatField(_("nota no Google"), null=True, blank=True)
    total_avaliacoes = models.PositiveIntegerField(_("total de avaliações"), null=True, blank=True)
    total_fotos = models.PositiveSmallIntegerField(_("total de fotos"), null=True, blank=True)
    status_google = models.CharField(_("situação no Google"), max_length=30, blank=True, default="")
    situacao_horario = models.CharField(
        _("situação do horário"), max_length=12, blank=True, default=""
    )
    horario_semana = models.JSONField(_("horário da semana"), default=list, blank=True)
    ultima_atividade_perfil = models.DateField(_("última atividade do perfil"), null=True, blank=True)
    google_maps_url = models.URLField(_("link do Google Maps"), max_length=500, blank=True, default="")
    analisado_places_em = models.DateTimeField(_("analisado no Google Places em"), null=True, blank=True)
    diagnostico = models.TextField(_("diagnóstico do motor de análise"), blank=True, default="")
    diagnostico_ia = models.TextField(_("diagnóstico da IA"), blank=True, default="")
    diagnostico_ia_em = models.DateTimeField(_("diagnóstico da IA gerado em"), null=True, blank=True)

    status_prospeccao = models.CharField(
        _("status da prospecção"),
        max_length=20,
        choices=Status.choices,
        default=Status.NOVA,
    )
    oportunidade_score = models.PositiveSmallIntegerField(
        _("score de oportunidade"),
        default=0,
        validators=[MaxValueValidator(100)],
    )
    observacoes = models.TextField(_("observações"), blank=True, default="")
    criado_em = models.DateTimeField(_("criado em"), auto_now_add=True)
    atualizado_em = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("empresa")
        verbose_name_plural = _("empresas")
        ordering = ("-oportunidade_score", "-criado_em")
        indexes = [
            models.Index(fields=["status_prospeccao"]),
            models.Index(fields=["-oportunidade_score"]),
        ]

    def __str__(self) -> str:
        return self.nome

    # -- Regras de domínio --------------------------------------------------
    @property
    def analisada_no_google(self) -> bool:
        """Indica se já há métricas da Google Places API para esta empresa."""
        return self.analisado_places_em is not None

    @property
    def fechada_permanentemente(self) -> bool:
        return self.status_google == STATUS_FECHADA_PERMANENTEMENTE

    def problemas_slugs(self, config: ConfiguracaoProspeccao | None = None) -> list[str]:
        """Slugs dos problemas detectados (mesmas regras de ``filtros_problema``).

        Scores desconhecidos (``None``), ``tem_ssl`` desconhecido e métricas do
        Google ainda não coletadas não geram problema.
        """
        config = config or ConfiguracaoProspeccao.obter()
        analisada = self.analisada_no_google
        atividade = self.ultima_atividade_perfil
        ativo = {
            "fechada": self.status_google == STATUS_FECHADA_PERMANENTEMENTE,
            "sem_site": not self.tem_site,
            "site_desatualizado": self.site_desatualizado,
            "apenas_instagram": self.apenas_instagram,
            "seo_fraco": self.score_seo is not None and self.score_seo < LIMIAR_SEO,
            "performance_baixa": self.score_performance is not None
            and self.score_performance < LIMIAR_PERFORMANCE,
            "sem_ssl": self.tem_ssl is False,
            "hospedagem_sem_site": self.hospedagem_sem_site,
            "nota_baixa": self.nota_google is not None and self.nota_google < config.limiar_nota,
            "poucas_avaliacoes": analisada
            and self.total_avaliacoes is not None
            and self.total_avaliacoes < config.limiar_avaliacoes,
            "sem_horario": self.situacao_horario == HORARIO_AUSENTE,
            "horario_incompleto": self.situacao_horario == HORARIO_INCOMPLETO,
            "poucas_fotos": analisada
            and self.total_fotos is not None
            and self.total_fotos < config.limiar_fotos,
            "perfil_desatualizado": analisada
            and (atividade is None or atividade < config.data_limite_atualizacao()),
        }
        return [slug for slug in PROBLEMAS if ativo.get(slug)]

    def rotulos_problemas(self, config: ConfiguracaoProspeccao | None = None) -> list[str]:
        """Lista os rótulos de problemas detectados nesta empresa."""
        return [rotulo_problema(slug) for slug in self.problemas_slugs(config)]

    def badges_problemas(self, config: ConfiguracaoProspeccao | None = None) -> list[dict]:
        """Problemas prontos para exibição: ``[{"slug", "rotulo", "cor"}]``."""
        return [
            {"slug": slug, "rotulo": rotulo_problema(slug), "cor": PROBLEMAS[slug][0]}
            for slug in self.problemas_slugs(config)
        ]

    def linha_dashboard(self, config: ConfiguracaoProspeccao | None = None) -> dict:
        """Retorna o dict ``EmpresaLinha`` (seção 7) com as chaves EXATAS.

        Além das chaves do contrato, inclui ``problemas_badges`` (rótulo + cor),
        ``nota_google`` e ``score`` para as tabelas do módulo.
        """
        badges = self.badges_problemas(config)
        return {
            "nome": self.nome or SEM_VALOR,
            "tempo_mercado": self.tempo_mercado_texto or SEM_VALOR,
            "responsavel": self.responsavel or SEM_VALOR,
            "email": self.email or SEM_VALOR,
            "instagram": self.instagram or SEM_VALOR,
            "dominio": self.dominio or SEM_VALOR,
            "whatsapp": self.whatsapp or SEM_VALOR,
            "problemas": [b["rotulo"] for b in badges],
            "problemas_badges": badges,
            "nota_google": self.nota_formatada or SEM_VALOR,
            "score": self.oportunidade_score,
            "inicial": self._inicial_avatar(),
            "cor": self._cor_avatar(),
            "pk": self.pk,
        }

    @property
    def nota_formatada(self) -> str:
        """Nota no padrão BR com o total de avaliações (ex.: ``"4,3 (27)"``)."""
        if self.nota_google is None:
            return ""
        nota = f"{self.nota_google:.1f}".replace(".", ",")
        if self.total_avaliacoes is not None:
            return f"{nota} ({self.total_avaliacoes})"
        return nota

    # -- Auxiliares de apresentação ----------------------------------------
    def _inicial_avatar(self) -> str:
        """Duas letras para o avatar (iniciais das duas primeiras palavras)."""
        nome = (self.nome or "").strip()
        if not nome:
            return "?"
        partes = [p for p in nome.split() if p]
        if len(partes) >= 2:
            return (partes[0][0] + partes[1][0]).upper()
        return nome[:2].upper()

    def _cor_avatar(self) -> str:
        """Cor de fundo determinística do avatar (estável para o mesmo nome)."""
        base = (self.nome or "").encode("utf-8")
        indice = int(hashlib.md5(base).hexdigest(), 16) % len(CORES_AVATAR)
        return CORES_AVATAR[indice]

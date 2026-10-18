"""Modelos do módulo Blog: taxonomia (Category/Tag) e conteúdo (Post).

Portado do template ``djangopress`` para a plataforma unificada. O autor do post
usa ``settings.AUTH_USER_MODEL`` (resolve para ``contas.Usuario``); não há
qualquer dependência de ``accounts``. Os campos de SEO/GEO/A11y guardam o
resultado da última validação executada no editor.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.blog import seo_utils


def unique_slugify(instance, value, slug_field="slug"):
    """Gera um slug único para o modelo, acrescentando sufixo numérico se preciso."""
    base = slugify(value)[:70] or "item"
    slug = base
    ModelClass = instance.__class__
    n = 2
    qs = ModelClass.objects.exclude(pk=instance.pk)
    while qs.filter(**{slug_field: slug}).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Category(models.Model):
    """Categoria de posts (hierárquica via ``parent``)."""

    name = models.CharField(_("Nome"), max_length=100)
    slug = models.SlugField(_("Slug"), max_length=110, unique=True, blank=True)
    description = models.TextField(_("Descrição"), blank=True)
    parent = models.ForeignKey(
        "self", verbose_name=_("Categoria pai"), null=True, blank=True,
        on_delete=models.SET_NULL, related_name="children",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Categoria")
        verbose_name_plural = _("Categorias")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:category_edit", args=[self.pk])


class Tag(models.Model):
    """Etiqueta livre associada a posts."""

    name = models.CharField(_("Nome"), max_length=60)
    slug = models.SlugField(_("Slug"), max_length=70, unique=True, blank=True)

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:tag_edit", args=[self.pk])


class PublishedManager(models.Manager):
    """Manager que retorna apenas posts publicados e visíveis."""

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(status=Post.Status.PUBLISHED, published_at__lte=timezone.now())
        )


class Post(models.Model):
    """Post do blog, com campos de conteúdo, SEO e resultado da validação."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Rascunho")
        PENDING = "pending", _("Aguardando revisão")
        SCHEDULED = "scheduled", _("Agendado")
        PUBLISHED = "published", _("Publicado")
        PRIVATE = "private", _("Privado")

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("Autor"), null=True,
        on_delete=models.SET_NULL, related_name="posts",
    )
    title = models.CharField(_("Título"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=210, unique=True, blank=True)
    excerpt = models.TextField(
        _("Resumo / TL;DR"), blank=True,
        help_text="Resumo curto que responde direto ao leitor (ótimo para SEO/GEO).",
    )
    content = models.TextField(_("Conteúdo (HTML)"), blank=True)

    featured_image = models.ImageField(_("Imagem de capa"), upload_to="posts/%Y/%m/", blank=True, null=True)
    featured_image_alt = models.CharField(_("Texto alternativo da capa"), max_length=200, blank=True)

    status = models.CharField(_("Status"), max_length=12, choices=Status.choices, default=Status.DRAFT)
    publish_at = models.DateTimeField(_("Publicar em (agendamento)"), null=True, blank=True)
    published_at = models.DateTimeField(_("Publicado em"), null=True, blank=True)

    categories = models.ManyToManyField(Category, verbose_name=_("Categorias"), blank=True, related_name="posts")
    tags = models.ManyToManyField(Tag, verbose_name=_("Tags"), blank=True, related_name="posts")

    # ---- SEO ----
    focus_keyword = models.CharField(_("Palavra-chave foco"), max_length=100, blank=True)
    meta_title = models.CharField(_("Meta title"), max_length=70, blank=True)
    meta_description = models.CharField(_("Meta description"), max_length=200, blank=True)
    canonical_url = models.URLField(_("URL canônica"), blank=True)
    og_image = models.ImageField(_("Imagem social (OG)"), upload_to="posts/og/%Y/%m/", blank=True, null=True)
    noindex = models.BooleanField(_("Não indexar (noindex)"), default=False)

    # ---- Resultado da última validação SEO/GEO/A11y ----
    seo_score = models.PositiveSmallIntegerField(default=0)
    geo_score = models.PositiveSmallIntegerField(default=0)
    a11y_score = models.PositiveSmallIntegerField(default=0)
    last_validation = models.JSONField(_("Último relatório de validação"), default=dict, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    views_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()      # manager padrão
    published = PublishedManager()  # apenas publicados/visíveis

    class Meta:
        verbose_name = _("Post")
        verbose_name_plural = _("Posts")
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:post_edit", args=[self.pk])

    # ------------------------------------------------------------------ #
    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED and bool(self.published_at) and self.published_at <= timezone.now()

    @property
    def display_meta_title(self):
        return self.meta_title or self.title

    @property
    def display_meta_description(self):
        return self.meta_description or self.excerpt or seo_utils.make_excerpt(self.content)

    @property
    def word_count(self):
        return seo_utils.word_count(self.content)

    @property
    def reading_time(self):
        return seo_utils.reading_time_minutes(self.content)

    def get_og_image_url(self):
        if self.og_image:
            return self.og_image.url
        if self.featured_image:
            return self.featured_image.url
        return ""

    def publish(self, when=None):
        """Marca como publicado imediatamente (ou na data informada)."""
        self.status = self.Status.PUBLISHED
        self.published_at = when or timezone.now()
        self.publish_at = None
        self.save(update_fields=["status", "published_at", "publish_at", "updated_at"])

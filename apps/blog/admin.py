"""Registro mínimo dos modelos do blog no admin do Django (opcional).

A gestão do dia a dia acontece no painel da plataforma (``/blog/``); este
registro serve apenas como ferramenta administrativa de apoio.
"""
from __future__ import annotations

from django.contrib import admin

from apps.blog.models import Category, Post, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "published_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "content")
    date_hierarchy = "created_at"
    autocomplete_fields = ("categories", "tags")
    readonly_fields = ("seo_score", "geo_score", "a11y_score", "validated_at", "views_count")

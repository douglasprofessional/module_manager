"""Formulários do módulo Blog (editor de posts + taxonomia).

Portado de ``djangopress``, trocando as classes do template antigo pelas do
design system da plataforma (``campo`` / ``campo-arquivo`` / ``textarea.campo``).
Sem Bootstrap. O status do post é definido pelos botões de ação da view, não
por um campo do formulário.
"""
from __future__ import annotations

from django import forms
from django.utils.text import slugify

from apps.blog.models import Category, Post, Tag

# Classe padrão dos campos de texto/select/url/number do design system.
CAMPO = {"class": "campo"}
CAMPO_ARQUIVO = {"class": "campo-arquivo"}


class PostForm(forms.ModelForm):
    """Formulário do editor de posts (o status é definido pelos botões de ação)."""

    new_tags = forms.CharField(
        label="Novas tags (separadas por vírgula)",
        required=False,
        widget=forms.TextInput(attrs={**CAMPO, "placeholder": "django, tutorial, web"}),
    )

    class Meta:
        model = Post
        fields = (
            "title", "slug", "excerpt", "content",
            "featured_image", "featured_image_alt",
            "categories", "tags",
            "focus_keyword", "meta_title", "meta_description",
            "canonical_url", "og_image", "noindex",
            "publish_at",
        )
        widgets = {
            "title": forms.TextInput(attrs={**CAMPO, "placeholder": "Título do post"}),
            "slug": forms.TextInput(attrs={**CAMPO, "placeholder": "gerado automaticamente se vazio"}),
            "excerpt": forms.Textarea(attrs={**CAMPO, "rows": 3, "placeholder": "Resumo / TL;DR — responda direto ao leitor"}),
            "content": forms.Textarea(attrs={**CAMPO, "rows": 18, "id": "id_content", "placeholder": "Escreva o conteúdo em HTML..."}),
            "featured_image": forms.ClearableFileInput(attrs=CAMPO_ARQUIVO),
            "featured_image_alt": forms.TextInput(attrs={**CAMPO, "placeholder": "Descreva a imagem de capa"}),
            "categories": forms.SelectMultiple(attrs={"class": "campo", "size": 5}),
            "tags": forms.SelectMultiple(attrs={"class": "campo", "size": 5}),
            "focus_keyword": forms.TextInput(attrs=CAMPO),
            "meta_title": forms.TextInput(attrs={**CAMPO, "maxlength": 70}),
            "meta_description": forms.Textarea(attrs={**CAMPO, "rows": 2, "maxlength": 200}),
            "canonical_url": forms.URLInput(attrs=CAMPO),
            "og_image": forms.ClearableFileInput(attrs=CAMPO_ARQUIVO),
            "noindex": forms.CheckboxInput(attrs={"class": "campo-check__entrada"}),
            "publish_at": forms.DateTimeInput(attrs={**CAMPO, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories"].required = False
        self.fields["tags"].required = False
        self.fields["content"].required = False
        # Aceita o formato do input datetime-local ao reexibir valores existentes.
        self.fields["publish_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]

    def save_tags(self, post):
        """Cria e associa as tags digitadas no campo `new_tags`."""
        raw = self.cleaned_data.get("new_tags", "")
        for name in [t.strip() for t in raw.split(",") if t.strip()]:
            tag, _ = Tag.objects.get_or_create(
                slug=slugify(name)[:70], defaults={"name": name}
            )
            post.tags.add(tag)


class CategoryForm(forms.ModelForm):
    """Cria/edita uma categoria."""

    class Meta:
        model = Category
        fields = ("name", "slug", "description", "parent")
        widgets = {
            "name": forms.TextInput(attrs=CAMPO),
            "slug": forms.TextInput(attrs={**CAMPO, "placeholder": "gerado automaticamente se vazio"}),
            "description": forms.Textarea(attrs={**CAMPO, "rows": 3}),
            "parent": forms.Select(attrs=CAMPO),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        # Evita que uma categoria seja pai dela mesma.
        if self.instance.pk:
            self.fields["parent"].queryset = Category.objects.exclude(pk=self.instance.pk)


class TagForm(forms.ModelForm):
    """Cria/edita uma tag."""

    class Meta:
        model = Tag
        fields = ("name", "slug")
        widgets = {
            "name": forms.TextInput(attrs=CAMPO),
            "slug": forms.TextInput(attrs={**CAMPO, "placeholder": "gerado automaticamente se vazio"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

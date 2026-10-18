"""Rotas do módulo Blog. Namespace: 'blog'.

Todas as telas são de GESTÃO INTERNA (exigem ``is_staff``). NÃO há rotas
públicas nem catch-all de slug na raiz (o site é admin-only por padrão). As
rotas ``*_create`` reusam a view de edição com ``pk=None`` para completar o CRUD
de categorias e tags (o item de menu "Novo post" aponta para ``post_create``).
"""
from __future__ import annotations

from django.urls import path

from apps.blog import views

app_name = "blog"

urlpatterns = [
    # Posts
    path("", views.lista, name="lista"),
    path("posts/novo/", views.post_edit, name="post_create"),
    path("posts/<int:pk>/editar/", views.post_edit, name="post_edit"),
    path("posts/<int:pk>/excluir/", views.post_delete, name="post_delete"),
    path("posts/validar/", views.validate_ajax, name="validate_ajax"),

    # Categorias
    path("categorias/", views.category_list, name="category_list"),
    path("categorias/nova/", views.category_edit, name="category_create"),
    path("categorias/<int:pk>/editar/", views.category_edit, name="category_edit"),
    path("categorias/<int:pk>/excluir/", views.category_delete, name="category_delete"),

    # Tags
    path("tags/", views.tag_list, name="tag_list"),
    path("tags/nova/", views.tag_edit, name="tag_create"),
    path("tags/<int:pk>/editar/", views.tag_edit, name="tag_edit"),
    path("tags/<int:pk>/excluir/", views.tag_delete, name="tag_delete"),
]

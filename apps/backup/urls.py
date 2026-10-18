"""Rotas do módulo de backup. Namespace: 'backup' (adendo 2 — MÓDULO 4)."""
from __future__ import annotations

from django.urls import path

from apps.backup import views

app_name = "backup"

urlpatterns = [
    path("", views.BackupListView.as_view(), name="lista"),
    path("novo/", views.novo, name="novo"),
    path("<int:pk>/baixar/", views.baixar, name="baixar"),
    path("<int:pk>/excluir/", views.excluir, name="excluir"),
]

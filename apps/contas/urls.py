"""Rotas do app de contas (autenticação). Namespace: 'contas'."""
from __future__ import annotations

from django.urls import path

from apps.contas import views

app_name = "contas"

urlpatterns = [
    path("entrar/", views.login_view, name="login"),
    path("sair/", views.logout_view, name="logout"),
    path("perfil/", views.perfil_view, name="perfil"),
]

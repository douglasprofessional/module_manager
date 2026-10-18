"""Rotas do núcleo.

Expõe o dashboard na raiz e o painel de Configurações Gerais do Sistema.
"""
from __future__ import annotations

from django.urls import path

from . import views

app_name = "nucleo"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("configuracoes/tema/", views.alternar_tema, name="alternar_tema"),
    path("configuracoes/modulo/", views.alternar_modulo, name="alternar_modulo"),
    path(
        "configuracoes/excluir-dados/",
        views.excluir_dados_modulo,
        name="excluir_dados_modulo",
    ),
]

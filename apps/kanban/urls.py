"""Rotas do módulo Kanban. Namespace: 'kanban' (adendo docs/SPEC_MODULOS.md)."""
from __future__ import annotations

from django.urls import path

from apps.kanban import views

app_name = "kanban"

urlpatterns = [
    path("", views.QuadroListView.as_view(), name="lista"),
    path("novo/", views.novo_quadro, name="novo_quadro"),
    path("<int:pk>/", views.QuadroDetailView.as_view(), name="quadro"),
    path("<int:pk>/colunas/nova/", views.nova_coluna, name="nova_coluna"),
    path("colunas/<int:pk>/cartoes/novo/", views.novo_cartao, name="novo_cartao"),
    path("cartoes/<int:pk>/mover/", views.mover_cartao, name="mover_cartao"),
    path("cartoes/<int:pk>/concluir/", views.alternar_concluido, name="concluir_cartao"),
]

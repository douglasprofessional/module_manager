"""Rotas do módulo de Monitoramento. Namespace: 'monitoramento' (adendo 2)."""
from __future__ import annotations

from django.urls import path

from apps.monitoramento import views

app_name = "monitoramento"

urlpatterns = [
    path("", views.ServidorListView.as_view(), name="lista"),
    path("novo/", views.novo, name="novo"),
    path("coletar-todos/", views.coletar_todos, name="coletar_todos"),
    path("<int:pk>/", views.ServidorDetailView.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/coletar/", views.coletar, name="coletar"),
    path("<int:pk>/excluir/", views.excluir, name="excluir"),
]

"""Rotas do módulo de SLA. Namespace: 'sla' (adendo docs/SPEC_MODULOS.md)."""
from __future__ import annotations

from django.urls import path

from apps.sla import views

app_name = "sla"

urlpatterns = [
    path("", views.ChamadoListView.as_view(), name="lista"),
    path("novo/", views.novo_chamado, name="novo_chamado"),
    path("politicas/", views.politicas, name="politicas"),
    path("<int:pk>/", views.ChamadoDetailView.as_view(), name="detalhe"),
    path("<int:pk>/responder/", views.registrar_resposta, name="registrar_resposta"),
    path("<int:pk>/resolver/", views.resolver, name="resolver"),
]

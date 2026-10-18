"""Rotas do módulo de prospecção. Namespace: 'prospeccao' (seção 3 da SPEC)."""
from __future__ import annotations

from django.urls import path

from apps.prospeccao import views

app_name = "prospeccao"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("empresas/", views.EmpresaListView.as_view(), name="lista"),
    path("empresas/<int:pk>/", views.EmpresaDetailView.as_view(), name="detalhe"),
    path("empresas/<int:pk>/atualizar-google/", views.atualizar_google, name="atualizar_google"),
    path("empresas/<int:pk>/diagnostico-ia/", views.diagnostico_ia, name="diagnostico_ia"),
    path("conexoes/", views.conexoes, name="conexoes"),
    path("buscas/nova/", views.nova_busca, name="nova_busca"),
    path("buscas/<int:pk>/executar/", views.executar_busca, name="executar_busca"),
]

"""Rotas do módulo de Marketing por E-mail. Namespace: 'email_marketing' (adendo 3).

A rota ``descadastrar`` é PÚBLICA (isenta pelo ``PUBLIC_URL_PREFIXES``); as demais
exigem administrador.
"""
from __future__ import annotations

from django.urls import path

from apps.email_marketing import views

app_name = "email_marketing"

urlpatterns = [
    # Campanhas
    path("", views.CampanhaListView.as_view(), name="campanhas"),
    path("campanhas/nova/", views.campanha_nova, name="campanha_nova"),
    path("campanhas/<int:pk>/", views.CampanhaDetailView.as_view(), name="campanha_detalhe"),
    path("campanhas/<int:pk>/enviar/", views.campanha_enviar, name="campanha_enviar"),
    # Configurações de envio
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("configuracoes/<int:pk>/testar/", views.config_testar, name="config_testar"),
    # Biblioteca de modelos (templates) de e-mail
    path("modelos/", views.templates_lista, name="templates"),
    path("modelos/<int:pk>/editar/", views.template_editar, name="template_editar"),
    path("modelos/<int:pk>/excluir/", views.template_excluir, name="template_excluir"),
    # Contatos e listas
    path("contatos/", views.contatos, name="contatos"),
    path("listas/", views.listas, name="listas"),
    # Descadastro público (GET confirma, POST efetiva)
    path("descadastrar/<str:token>/", views.descadastrar, name="descadastrar"),
]

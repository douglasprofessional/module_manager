"""Rotas do modulo de Cupons (painel, cupons, aplicacoes, cobrancas, clientes)."""

from django.urls import path

from apps.cupons import views

app_name = "cupons"

urlpatterns = [
    # Painel (antiga core.dashboard): KPIs + tabela de clientes.
    path("", views.painel, name="painel"),

    # Cupons
    path("cupons/", views.coupon_list, name="list"),
    path("cupons/novo/", views.coupon_create, name="create"),
    path("cupons/<int:pk>/editar/", views.coupon_update, name="update"),
    path("cupons/<int:pk>/excluir/", views.coupon_delete, name="delete"),

    # Aplicacao de cupons
    path("aplicar/<int:customer_id>/", views.assignment_create, name="assignment_create"),
    path("aplicacoes/<int:pk>/remover/", views.assignment_delete, name="assignment_delete"),

    # Cobrancas mensais
    path("cobrancas/", views.charge_list, name="charge_list"),
    path("cobrancas/gerar/", views.charge_generate, name="charge_generate"),
    path("cobrancas/<int:pk>/situacao/", views.charge_update_status, name="charge_status"),
    path("cobrancas/<int:pk>/editar/", views.charge_edit, name="charge_edit"),

    # Clientes
    path("clientes/", views.cliente_lista, name="cliente_lista"),
    path("clientes/novo/", views.customer_create, name="customer_create"),
    path("clientes/<int:pk>/", views.customer_detail, name="customer_detail"),
    path("clientes/<int:pk>/editar/", views.customer_update, name="customer_update"),
    path("clientes/<int:pk>/excluir/", views.customer_delete, name="customer_delete"),
    path("clientes/<int:pk>/situacao/", views.customer_toggle_active, name="customer_toggle_active"),
]

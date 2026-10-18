"""Admin do módulo de Marketing por E-mail (adendo 3 — MÓDULO 5).

Regra de segurança (seção 9): a senha SMTP NUNCA é exposta no admin — nem em
texto, nem o token cifrado editável. O admin mostra apenas se há senha
configurada. ``EnvioEmail`` é somente leitura (log gerado pelo envio).
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.email_marketing.models import (
    Campanha,
    ConfiguracaoEnvio,
    Contato,
    EnvioEmail,
    Lista,
)


@admin.register(ConfiguracaoEnvio)
class ConfiguracaoEnvioAdmin(admin.ModelAdmin):
    """Admin de configurações: expõe o estado da senha, nunca o valor."""

    list_display = (
        "nome",
        "tipo",
        "email_remetente",
        "ativo",
        "tem_senha",
        "criado_em",
    )
    list_filter = ("tipo", "ativo", "usar_tls", "usar_ssl", "criado_em")
    search_fields = ("nome", "email_remetente", "host", "usuario")
    readonly_fields = ("tem_senha", "criado_em", "atualizado_em")
    # A senha cifrada nunca aparece no formulário do admin.
    exclude = ("senha_criptografada",)

    @admin.display(boolean=True, description=_("senha configurada"))
    def tem_senha(self, obj: ConfiguracaoEnvio) -> bool:
        return obj.tem_senha


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    """Admin de contatos: permite marcar/desmarcar 'inscrito' rapidamente."""

    list_display = ("email", "nome", "empresa", "inscrito", "origem", "criado_em")
    list_filter = ("inscrito", "criado_em")
    list_editable = ("inscrito",)
    search_fields = ("email", "nome", "empresa", "tags")
    # O token nunca é editável; é gerado no modelo e usado no link público.
    readonly_fields = ("token_descadastro", "descadastrado_em", "criado_em")
    ordering = ("email",)


@admin.register(Lista)
class ListaAdmin(admin.ModelAdmin):
    """Admin de listas: seleção de contatos por filtro horizontal."""

    list_display = ("nome", "criado_em")
    search_fields = ("nome", "descricao")
    readonly_fields = ("criado_em",)
    filter_horizontal = ("contatos",)


@admin.register(Campanha)
class CampanhaAdmin(admin.ModelAdmin):
    """Admin de campanhas: acompanha status e contadores (contadores read-only)."""

    list_display = (
        "nome",
        "status",
        "configuracao",
        "lista",
        "total_destinatarios",
        "total_enviados",
        "total_falhas",
        "criado_em",
    )
    list_filter = ("status", "configuracao", "criado_em")
    search_fields = ("nome", "assunto")
    readonly_fields = (
        "status",
        "total_destinatarios",
        "total_enviados",
        "total_falhas",
        "criado_em",
        "enviada_em",
    )
    list_select_related = ("configuracao", "lista")
    autocomplete_fields = ("configuracao", "lista")


@admin.register(EnvioEmail)
class EnvioEmailAdmin(admin.ModelAdmin):
    """Admin de envios: log somente leitura por destinatário."""

    list_display = ("email", "campanha", "status", "enviado_em", "criado_em")
    list_filter = ("status", "criado_em")
    search_fields = ("email", "campanha__nome")
    list_select_related = ("campanha", "contato")
    date_hierarchy = "criado_em"
    readonly_fields = (
        "campanha",
        "contato",
        "email",
        "status",
        "erro",
        "enviado_em",
        "criado_em",
    )

    def has_add_permission(self, request) -> bool:
        # Os envios são gerados pelo disparo da campanha, não criados manualmente.
        return False

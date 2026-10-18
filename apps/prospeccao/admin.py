"""Admin do módulo de prospecção.

Regra de segurança (seção 9): a chave da API NUNCA é exposta no admin — nem em
texto, nem o token cifrado editável. O admin mostra apenas se há chave
configurada. ``Empresa`` e ``Busca`` recebem ``list_display`` úteis para
operação.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.prospeccao.models import Busca, ConexaoGoogle, ConfiguracaoProspeccao, Empresa


@admin.register(ConexaoGoogle)
class ConexaoGoogleAdmin(admin.ModelAdmin):
    """Admin de conexões: expõe o estado da chave, nunca o valor."""

    list_display = ("nome", "ativo", "tem_chave", "criado_por", "criado_em", "atualizado_em")
    list_filter = ("ativo", "criado_em")
    search_fields = ("nome",)
    readonly_fields = ("tem_chave", "criado_em", "atualizado_em")
    # A chave cifrada nunca aparece no formulário do admin.
    exclude = ("chave_api_criptografada",)

    @admin.display(boolean=True, description=_("chave configurada"))
    def tem_chave(self, obj: ConexaoGoogle) -> bool:
        return obj.tem_chave


@admin.register(ConfiguracaoProspeccao)
class ConfiguracaoProspeccaoAdmin(admin.ModelAdmin):
    """Configuração do Painel: mostra se há chaves, nunca os valores."""

    list_display = ("__str__", "tem_chave_google", "tem_ia_chave", "ia_modelo", "ia_ativa", "atualizado_em")
    readonly_fields = ("tem_chave_google", "tem_ia_chave", "atualizado_em")
    # As chaves cifradas nunca aparecem no formulário do admin (use o Painel).
    exclude = ("chave_google_criptografada", "ia_chave_criptografada")

    @admin.display(boolean=True, description=_("chave do Google configurada"))
    def tem_chave_google(self, obj: ConfiguracaoProspeccao) -> bool:
        return obj.tem_chave_google

    @admin.display(boolean=True, description=_("chave da IA configurada"))
    def tem_ia_chave(self, obj: ConfiguracaoProspeccao) -> bool:
        return obj.tem_ia_chave

    def has_add_permission(self, request) -> bool:
        # Singleton: a linha única é criada pelo Painel do módulo.
        return not ConfiguracaoProspeccao.objects.exists()


@admin.register(Busca)
class BuscaAdmin(admin.ModelAdmin):
    """Admin de buscas: acompanha status e resultados."""

    list_display = (
        "termo",
        "localizacao",
        "raio_metros",
        "status",
        "total_resultados",
        "conexao",
        "criado_por",
        "criado_em",
    )
    list_filter = ("status", "criado_em")
    search_fields = ("termo", "localizacao")
    readonly_fields = ("criado_em",)
    autocomplete_fields = ("conexao",)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    """Admin de empresas: visão operacional de leads e problemas."""

    list_display = (
        "nome",
        "categoria",
        "status_prospeccao",
        "oportunidade_score",
        "tem_site",
        "tem_ssl",
        "nota_google",
        "total_avaliacoes",
        "status_google",
        "dominio",
        "criado_em",
    )
    list_filter = (
        "status_prospeccao",
        "tem_site",
        "tem_ssl",
        "apenas_instagram",
        "site_desatualizado",
        "hospedagem_sem_site",
        "status_google",
        "situacao_horario",
        "criado_em",
    )
    search_fields = ("nome", "dominio", "email", "instagram", "responsavel")
    readonly_fields = ("criado_em", "atualizado_em", "analisado_places_em", "diagnostico_ia_em")
    list_select_related = ("busca",)
    ordering = ("-oportunidade_score", "-criado_em")

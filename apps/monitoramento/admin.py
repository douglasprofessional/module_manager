"""Admin do módulo de Monitoramento.

Regra de segurança (seção 9): os segredos (senha/chave/passphrase) NUNCA são
expostos no admin — nem em texto, nem os tokens cifrados editáveis. O admin
mostra apenas se há credencial configurada. ``LeituraMetrica`` é somente leitura
(histórico de coletas).
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.monitoramento.models import LeituraMetrica, ServidorVPS


@admin.register(ServidorVPS)
class ServidorVPSAdmin(admin.ModelAdmin):
    """Admin de servidores: expõe o estado da credencial, nunca o valor."""

    list_display = (
        "nome",
        "host",
        "usuario",
        "metodo_auth",
        "ultimo_status",
        "ultima_coleta_em",
        "ativo",
    )
    list_filter = ("ultimo_status", "ativo", "metodo_auth", "provedor")
    search_fields = ("nome", "host", "provedor", "tags")
    readonly_fields = (
        "tem_credencial",
        "host_key_fingerprint",
        "ultimo_status",
        "ultima_coleta_em",
        "criado_em",
        "atualizado_em",
    )
    # Os tokens cifrados nunca aparecem no formulário do admin.
    exclude = (
        "senha_criptografada",
        "chave_privada_criptografada",
        "passphrase_criptografada",
    )

    @admin.display(boolean=True, description=_("credencial configurada"))
    def tem_credencial(self, obj: ServidorVPS) -> bool:
        return obj.tem_credencial


@admin.register(LeituraMetrica)
class LeituraMetricaAdmin(admin.ModelAdmin):
    """Admin de leituras: histórico somente leitura de métricas."""

    list_display = (
        "servidor",
        "coletado_em",
        "online",
        "cpu_pct",
        "mem_pct",
        "disco_pct",
        "sistema",
    )
    list_filter = ("online", "coletado_em")
    search_fields = ("servidor__nome", "servidor__host", "sistema")
    list_select_related = ("servidor",)
    date_hierarchy = "coletado_em"
    readonly_fields = (
        "servidor",
        "coletado_em",
        "online",
        "cpu_pct",
        "mem_pct",
        "mem_total_mb",
        "mem_usada_mb",
        "disco_pct",
        "disco_total_gb",
        "disco_usado_gb",
        "uptime_segundos",
        "carga1",
        "carga5",
        "carga15",
        "nucleos",
        "sistema",
        "erro",
    )

    def has_add_permission(self, request) -> bool:
        # Leituras são geradas pela coleta, não criadas manualmente.
        return False

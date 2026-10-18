"""
Invalidacao de cache.

Qualquer alteracao em clientes, cupons, aplicacoes ou cobrancas incrementa a
versao do cache do painel - assim as metricas nunca ficam desatualizadas sem
precisar varrer chaves no cache.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.cupons.models import Coupon, CouponAssignment, Customer, MonthlyCharge
from apps.cupons.services import bump_dashboard_version

MODELOS_MONITORADOS = (Customer, Coupon, CouponAssignment, MonthlyCharge)


@receiver(post_save, dispatch_uid="cupons_cache_post_save")
def _invalidar_cache_ao_salvar(sender, **kwargs):
    if sender in MODELOS_MONITORADOS:
        bump_dashboard_version()


@receiver(post_delete, dispatch_uid="cupons_cache_post_delete")
def _invalidar_cache_ao_excluir(sender, **kwargs):
    if sender in MODELOS_MONITORADOS:
        bump_dashboard_version()

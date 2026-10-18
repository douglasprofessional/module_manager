"""Admin do modulo de Cupons (registro minimo e seguro dos 4 modelos)."""

from __future__ import annotations

from django.contrib import admin

from apps.cupons.models import Coupon, CouponAssignment, Customer, MonthlyCharge


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """Admin de clientes."""

    list_display = (
        "full_name",
        "email",
        "phone",
        "recurring_fee",
        "is_active",
        "is_delinquent",
        "created_at",
    )
    list_filter = ("is_active", "is_delinquent", "monthly_invoice")
    search_fields = ("full_name", "email", "phone")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("full_name",)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    """Admin de cupons."""

    list_display = (
        "name",
        "code",
        "discount_type",
        "value",
        "is_active",
        "is_birthday",
        "start_date",
        "end_date",
    )
    list_filter = ("discount_type", "is_active", "is_birthday")
    search_fields = ("name", "code", "description")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-is_birthday", "name")


@admin.register(CouponAssignment)
class CouponAssignmentAdmin(admin.ModelAdmin):
    """Admin de aplicacoes de cupom."""

    list_display = (
        "customer",
        "coupon",
        "mode",
        "start_month",
        "end_month",
        "origin",
        "is_active",
    )
    list_filter = ("mode", "origin", "is_active")
    search_fields = ("customer__full_name", "coupon__name", "coupon__code")
    autocomplete_fields = ("customer", "coupon")
    list_select_related = ("customer", "coupon")
    readonly_fields = ("created_at",)


@admin.register(MonthlyCharge)
class MonthlyChargeAdmin(admin.ModelAdmin):
    """Admin de cobrancas mensais."""

    list_display = (
        "customer",
        "reference_month",
        "base_amount",
        "discount_amount",
        "final_amount",
        "status",
        "due_date",
    )
    list_filter = ("status", "reference_month", "invoice_required")
    search_fields = ("customer__full_name", "customer__email")
    list_select_related = ("customer",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "reference_month"

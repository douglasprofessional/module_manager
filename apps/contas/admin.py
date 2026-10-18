"""Admin do modelo de usuário, com senha em hash e sem exibir dados sensíveis."""
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.contrib.auth import password_validation
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.translation import gettext_lazy as _

from apps.contas.models import Usuario


class UsuarioCriacaoForm(forms.ModelForm):
    """Formulário de criação: coleta a senha e a valida antes de aplicar o hash."""

    senha1 = forms.CharField(
        label=_("Senha"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    senha2 = forms.CharField(
        label=_("Confirmação de senha"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("Repita a senha para verificação."),
    )

    class Meta:
        model = Usuario
        fields = ("email", "nome_completo")

    def clean_senha2(self) -> str:
        senha1 = self.cleaned_data.get("senha1")
        senha2 = self.cleaned_data.get("senha2")
        if senha1 and senha2 and senha1 != senha2:
            raise forms.ValidationError(_("As senhas não coincidem."), code="senha_diferente")
        return senha2

    def _post_clean(self) -> None:
        super()._post_clean()
        senha = self.cleaned_data.get("senha2")
        if senha:
            try:
                password_validation.validate_password(senha, self.instance)
            except forms.ValidationError as erro:
                self.add_error("senha2", erro)

    def save(self, commit: bool = True) -> Usuario:
        usuario = super().save(commit=False)
        usuario.set_password(self.cleaned_data["senha1"])
        if commit:
            usuario.save()
        return usuario


class UsuarioAlteracaoForm(forms.ModelForm):
    """Formulário de alteração: exibe apenas o hash da senha (nunca o texto)."""

    password = ReadOnlyPasswordHashField(
        label=_("Senha"),
        help_text=_(
            "As senhas são armazenadas em hash — não é possível vê-las. "
            "Você pode alterá-la usando <a href=\"{}\">este formulário</a>."
        ),
    )

    class Meta:
        model = Usuario
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        campo_senha = self.fields.get("password")
        if campo_senha is not None:
            campo_senha.help_text = campo_senha.help_text.format("../password/")

    def clean_password(self) -> Any:
        # Ignora qualquer entrada; mantém o hash já armazenado.
        return self.initial.get("password")


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin adaptado ao modelo ``Usuario`` (login por e-mail, sem username)."""

    add_form = UsuarioCriacaoForm
    form = UsuarioAlteracaoForm
    model = Usuario

    list_display = ("email", "nome_completo", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "nome_completo")
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = ("last_login", "date_joined", "ultimo_ip")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Informações pessoais"), {"fields": ("nome_completo",)}),
        (
            _("Permissões"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Datas importantes"), {"fields": ("last_login", "date_joined", "ultimo_ip")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nome_completo", "senha1", "senha2"),
            },
        ),
    )

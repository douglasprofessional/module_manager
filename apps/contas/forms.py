"""Formulários de autenticação e de perfil.

- ``LoginForm``: login com mensagens genéricas (protege contra enumeração).
- ``PerfilForm``: edição do próprio perfil (nome, e-mail, foto, tema).
- ``AlterarSenhaForm``: troca de senha com validadores do Django.
"""
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import authenticate, password_validation
from django.utils.translation import gettext_lazy as _

from apps.contas.models import Usuario


class LoginForm(forms.Form):
    """Formulário de autenticação por e-mail e senha.

    Nunca revela se o e-mail existe: qualquer falha (e-mail inexistente,
    senha incorreta, conta inativa ou sem acesso) produz a MESMA mensagem.
    """

    email = forms.EmailField(
        label=_("E-mail"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    senha = forms.CharField(
        label=_("Senha"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    mensagens_erro = {
        "invalido": _("E-mail ou senha inválidos."),
    }

    def __init__(self, request: Any = None, *args: Any, **kwargs: Any) -> None:
        """``request`` é usado por ``authenticate`` (mesma assinatura do Django)."""
        self.request = request
        self.usuario = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        dados = super().clean()
        email = dados.get("email")
        senha = dados.get("senha")

        if email and senha:
            # ModelBackend usa USERNAME_FIELD='email'; retorna None p/ inativos.
            self.usuario = authenticate(self.request, username=email, password=senha)
            # Mensagem genérica para credenciais inválidas OU falta de acesso (is_staff),
            # evitando qualquer forma de enumeração de usuários.
            if self.usuario is None or not self.usuario.is_staff:
                self.usuario = None
                raise forms.ValidationError(
                    self.mensagens_erro["invalido"], code="invalido"
                )
        return dados

    def get_usuario(self):
        """Retorna o usuário autenticado (ou None se a validação falhou)."""
        return self.usuario


class PerfilForm(forms.ModelForm):
    """Edição do próprio perfil: nome, e-mail, foto e tema."""

    class Meta:
        model = Usuario
        fields = ["nome_completo", "email", "foto", "tema"]
        widgets = {
            "nome_completo": forms.TextInput(
                attrs={"class": "campo", "autocomplete": "name"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "campo", "autocomplete": "email"}
            ),
            "foto": forms.ClearableFileInput(
                attrs={"class": "campo-arquivo", "accept": ".png,.jpg,.jpeg,.webp,.gif"}
            ),
            "tema": forms.Select(attrs={"class": "campo"}),
        }

    def clean_email(self) -> str:
        """Garante e-mail único (case-insensitive), ignorando o próprio usuário."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        qs = Usuario.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("Já existe uma conta com este e-mail."))
        return email


class AlterarSenhaForm(forms.Form):
    """Troca de senha do próprio usuário (exige a senha atual)."""

    senha_atual = forms.CharField(
        label=_("Senha atual"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "campo", "autocomplete": "current-password"}
        ),
    )
    nova_senha = forms.CharField(
        label=_("Nova senha"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "campo", "autocomplete": "new-password"}
        ),
    )
    confirmar_senha = forms.CharField(
        label=_("Confirmar nova senha"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "campo", "autocomplete": "new-password"}
        ),
    )

    def __init__(self, usuario: Usuario, *args: Any, **kwargs: Any) -> None:
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean_senha_atual(self) -> str:
        senha = self.cleaned_data.get("senha_atual") or ""
        if not self.usuario.check_password(senha):
            raise forms.ValidationError(_("Senha atual incorreta."))
        return senha

    def clean(self) -> dict[str, Any]:
        dados = super().clean()
        nova = dados.get("nova_senha")
        confirmar = dados.get("confirmar_senha")
        if nova and confirmar and nova != confirmar:
            self.add_error("confirmar_senha", _("As senhas não coincidem."))
        if nova:
            password_validation.validate_password(nova, self.usuario)
        return dados


"""Formulários do módulo de Monitoramento (adendo 2 — MÓDULO 3).

``ServidorForm`` cria/edita um ``ServidorVPS``. Os segredos (senha, chave
privada e passphrase) chegam por campos WRITE-ONLY e são persistidos cifrados
(via as properties do modelo). Ao EDITAR, esses campos ficam VAZIOS e só
sobrescrevem a credencial se forem preenchidos — deixá-los em branco MANTÉM a
credencial existente. As chaves nunca são pré-preenchidas nem exibidas.

Validações: porta 1..65535; host obrigatório; e, na CRIAÇÃO com
``metodo_auth=chave``, a chave privada é obrigatória.
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.monitoramento.models import ServidorVPS

PORTA_MINIMA = 1
PORTA_MAXIMA = 65535


class ServidorForm(forms.ModelForm):
    """Cria/edita um ``ServidorVPS`` recebendo os segredos de forma write-only."""

    senha = forms.CharField(
        label=_("Senha"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": "••••••••"},
        ),
        help_text=_("Usada quando o método é 'Senha'. Em branco ao editar = manter."),
    )
    chave_privada = forms.CharField(
        label=_("Chave privada"),
        required=False,
        strip=False,
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "autocomplete": "off",
                "placeholder": "-----BEGIN OPENSSH PRIVATE KEY-----",
                "spellcheck": "false",
            }
        ),
        help_text=_("Usada quando o método é 'Chave privada'. Em branco ao editar = manter."),
    )
    passphrase = forms.CharField(
        label=_("Passphrase da chave"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": "••••••••"},
        ),
        help_text=_("Opcional. Em branco ao editar = manter."),
    )
    resetar_host_key = forms.BooleanField(
        label=_("Redefinir a host key aprendida (TOFU)"),
        required=False,
        help_text=_(
            "Marque para esquecer o fingerprint atual e reaprendê-lo na próxima "
            "coleta (use somente se você trocou/reinstalou o servidor)."
        ),
    )

    class Meta:
        model = ServidorVPS
        fields = (
            "nome",
            "host",
            "porta_ssh",
            "usuario",
            "metodo_auth",
            "provedor",
            "tags",
            "observacoes",
            "ativo",
        )
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: web-01")}),
            "host": forms.TextInput(attrs={"placeholder": _("Ex.: 203.0.113.10 ou vps.exemplo.com")}),
            "porta_ssh": forms.NumberInput(
                attrs={"min": PORTA_MINIMA, "max": PORTA_MAXIMA, "step": 1}
            ),
            "usuario": forms.TextInput(attrs={"placeholder": "root"}),
            "provedor": forms.TextInput(attrs={"placeholder": _("Ex.: Hetzner, DigitalOcean")}),
            "tags": forms.TextInput(attrs={"placeholder": _("Ex.: produção, web")}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_host(self) -> str:
        host = (self.cleaned_data.get("host") or "").strip()
        if not host:
            raise forms.ValidationError(_("Informe o host (IP ou domínio)."), code="obrigatorio")
        if " " in host or len(host) > 255:
            raise forms.ValidationError(_("Host inválido."), code="formato")
        return host

    def clean_porta_ssh(self) -> int:
        porta = self.cleaned_data.get("porta_ssh")
        if porta is None:
            raise forms.ValidationError(_("Informe a porta SSH."), code="obrigatorio")
        if not (PORTA_MINIMA <= porta <= PORTA_MAXIMA):
            raise forms.ValidationError(
                _("A porta deve estar entre %(min)d e %(max)d.")
                % {"min": PORTA_MINIMA, "max": PORTA_MAXIMA},
                code="intervalo",
            )
        return porta

    def clean_usuario(self) -> str:
        usuario = (self.cleaned_data.get("usuario") or "").strip()
        if not usuario:
            raise forms.ValidationError(_("Informe o usuário SSH."), code="obrigatorio")
        return usuario

    def clean(self):
        dados = super().clean()
        metodo = dados.get("metodo_auth")
        criando = self.instance.pk is None
        if metodo == ServidorVPS.MetodoAuth.CHAVE and criando:
            # Na criação por chave, a chave privada é obrigatória.
            if not (dados.get("chave_privada") or "").strip():
                self.add_error(
                    "chave_privada",
                    _("Informe a chave privada para autenticação por chave."),
                )
        return dados

    def save(self, commit: bool = True) -> ServidorVPS:
        """Aplica os segredos via properties (que cifram) apenas se preenchidos."""
        servidor = super().save(commit=False)

        senha = self.cleaned_data.get("senha") or ""
        chave = self.cleaned_data.get("chave_privada") or ""
        passphrase = self.cleaned_data.get("passphrase") or ""

        # Em branco = manter o valor existente (não apaga a credencial ao editar).
        if senha:
            servidor.senha = senha
        if chave.strip():
            servidor.chave_privada = chave
        if passphrase:
            servidor.passphrase = passphrase

        if self.cleaned_data.get("resetar_host_key"):
            servidor.host_key_fingerprint = ""

        if commit:
            servidor.save()
        return servidor

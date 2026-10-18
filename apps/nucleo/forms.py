"""Formulários do núcleo (Configurações Gerais do Sistema)."""
from __future__ import annotations

from django import forms

from apps.nucleo.models import ConfiguracaoSistema


class ConfiguracaoSistemaForm(forms.ModelForm):
    """Edição da marca branca: nome do sistema, logo e tema padrão."""

    class Meta:
        model = ConfiguracaoSistema
        fields = ["nome_sistema", "logo", "tema_padrao"]
        widgets = {
            "nome_sistema": forms.TextInput(
                attrs={"class": "campo", "maxlength": 80, "autocomplete": "off"}
            ),
            "logo": forms.ClearableFileInput(
                attrs={"class": "campo-arquivo", "accept": ".png,.jpg,.jpeg,.webp,.svg"}
            ),
            "tema_padrao": forms.Select(attrs={"class": "campo"}),
        }

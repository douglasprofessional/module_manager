"""Formulários do módulo Kanban (adendo docs/SPEC_MODULOS.md — MÓDULO 1).

- ``QuadroForm``: cria/edita um quadro (nome, descrição).
- ``ColunaForm``: cria uma coluna (nome, limite de WIP, cor).
- ``CartaoForm``: cria/edita um cartão (título, descrição, prioridade,
  responsável e prazo — usando ``DateInput`` ``type="date"``). Os campos de
  ordenação/estado são controlados pelas views, não pelo formulário.
"""
from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.kanban.models import Cartao, Coluna, Quadro

Usuario = get_user_model()


class QuadroForm(forms.ModelForm):
    """Cria/edita um ``Quadro`` (nome obrigatório, descrição opcional)."""

    class Meta:
        model = Quadro
        fields = ("nome", "descricao")
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: Comercial")}),
            "descricao": forms.Textarea(
                attrs={"rows": 3, "placeholder": _("Para que serve este quadro?")}
            ),
        }

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 2:
            raise forms.ValidationError(
                _("O nome deve ter ao menos 2 caracteres."), code="curto"
            )
        return nome


class ColunaForm(forms.ModelForm):
    """Cria uma ``Coluna`` (nome, limite de WIP opcional e cor)."""

    class Meta:
        model = Coluna
        fields = ("nome", "limite_wip", "cor")
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: Em andamento")}),
            "limite_wip": forms.NumberInput(attrs={"min": 1, "step": 1}),
            "cor": forms.TextInput(attrs={"type": "color"}),
        }

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if not nome:
            raise forms.ValidationError(_("Informe o nome da coluna."), code="obrigatorio")
        return nome


class CartaoForm(forms.ModelForm):
    """Cria/edita um ``Cartao`` (prazo via ``DateInput`` ``type="date"``)."""

    class Meta:
        model = Cartao
        fields = ("titulo", "descricao", "prioridade", "responsavel", "prazo")
        widgets = {
            "titulo": forms.TextInput(attrs={"placeholder": _("Ex.: Ligar para o cliente")}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "prazo": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Só usuários com acesso ao sistema (admins) podem ser responsáveis.
        self.fields["responsavel"].queryset = Usuario.objects.filter(
            is_active=True, is_staff=True
        ).order_by("nome_completo", "email")
        self.fields["responsavel"].required = False
        self.fields["responsavel"].empty_label = _("Sem responsável")
        # Aceita o valor vindo do <input type="date"> (ISO) na revalidação.
        self.fields["prazo"].input_formats = ["%Y-%m-%d"]

    def clean_titulo(self) -> str:
        titulo = (self.cleaned_data.get("titulo") or "").strip()
        if len(titulo) < 2:
            raise forms.ValidationError(
                _("O título deve ter ao menos 2 caracteres."), code="curto"
            )
        return titulo

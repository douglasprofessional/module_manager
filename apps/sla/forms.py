"""Formulários do módulo de SLA (adendo docs/SPEC_MODULOS.md — MÓDULO 2).

- ``ChamadoForm``: cria/edita um chamado. Os prazos (``prazo_resposta`` e
  ``prazo_resolucao``) NÃO fazem parte do formulário — são calculados no
  ``Chamado.save()`` a partir da política e de ``aberto_em``.
- ``PoliticaForm``: cria/edita uma política de SLA (prazos em horas).
"""
from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.sla.models import Chamado, Politica

# Limites defensivos para os prazos (em horas).
PRAZO_MINIMO_HORAS = 1
PRAZO_MAXIMO_HORAS = 8_760  # 365 dias


class ChamadoForm(forms.ModelForm):
    """Cria/edita um ``Chamado``. Os prazos são calculados no modelo."""

    class Meta:
        model = Chamado
        fields = (
            "titulo",
            "descricao",
            "politica",
            "prioridade",
            "solicitante",
            "responsavel",
        )
        widgets = {
            "titulo": forms.TextInput(
                attrs={"placeholder": _("Ex.: Site fora do ar")}
            ),
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "solicitante": forms.TextInput(
                attrs={"placeholder": _("Ex.: Maria (Financeiro)")}
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Só políticas ativas podem reger um novo chamado.
        self.fields["politica"].queryset = Politica.objects.filter(ativo=True)
        self.fields["politica"].empty_label = _("Selecione uma política")
        self.fields["responsavel"].required = False
        self.fields["responsavel"].empty_label = _("Sem responsável")

    def clean_titulo(self) -> str:
        titulo = (self.cleaned_data.get("titulo") or "").strip()
        if len(titulo) < 3:
            raise forms.ValidationError(
                _("O título deve ter ao menos 3 caracteres."), code="curto"
            )
        return titulo


class PoliticaForm(forms.ModelForm):
    """Cria/edita uma ``Politica`` de SLA (prazos em horas)."""

    class Meta:
        model = Politica
        fields = (
            "nome",
            "descricao",
            "prazo_resposta_horas",
            "prazo_resolucao_horas",
            "ativo",
        )
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: Padrão")}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "prazo_resposta_horas": forms.NumberInput(
                attrs={"min": PRAZO_MINIMO_HORAS, "max": PRAZO_MAXIMO_HORAS, "step": 1}
            ),
            "prazo_resolucao_horas": forms.NumberInput(
                attrs={"min": PRAZO_MINIMO_HORAS, "max": PRAZO_MAXIMO_HORAS, "step": 1}
            ),
        }

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 2:
            raise forms.ValidationError(
                _("O nome deve ter ao menos 2 caracteres."), code="curto"
            )
        return nome

    def _validar_prazo(self, campo: str) -> int:
        valor = self.cleaned_data.get(campo)
        if valor is None:
            raise forms.ValidationError(_("Informe o prazo em horas."), code="obrigatorio")
        if not (PRAZO_MINIMO_HORAS <= valor <= PRAZO_MAXIMO_HORAS):
            raise forms.ValidationError(
                _("O prazo deve estar entre %(min)d e %(max)d horas.")
                % {"min": PRAZO_MINIMO_HORAS, "max": PRAZO_MAXIMO_HORAS},
                code="intervalo",
            )
        return valor

    def clean_prazo_resposta_horas(self) -> int:
        return self._validar_prazo("prazo_resposta_horas")

    def clean_prazo_resolucao_horas(self) -> int:
        return self._validar_prazo("prazo_resolucao_horas")

    def clean(self) -> dict:
        """Garante que a resolução não seja mais curta que a resposta."""
        dados = super().clean()
        resposta = dados.get("prazo_resposta_horas")
        resolucao = dados.get("prazo_resolucao_horas")
        if resposta is not None and resolucao is not None and resolucao < resposta:
            self.add_error(
                "prazo_resolucao_horas",
                forms.ValidationError(
                    _("A resolução não pode ser mais curta que a resposta."),
                    code="incoerente",
                ),
            )
        return dados

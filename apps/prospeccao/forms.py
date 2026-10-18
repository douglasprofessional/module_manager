"""Formulários do módulo de prospecção (seção 13 da SPEC).

- ``ConexaoGoogleForm``: coleta a chave da API por um campo write-only
  (``PasswordInput``) e a persiste cifrada (via a property ``chave_api`` do
  modelo). A chave nunca é pré-preenchida nem exibida.
- ``BuscaForm``: valida termo, localização, raio e conexão (opcional; apenas
  conexões ativas), com limites fortes.
- ``ChaveGoogleForm``: campo do Painel do módulo para colar/salvar a chave da
  Google Places API (New) — cifrada, write-only.
- ``IAForm``: chave (write-only), modelo e liga/desliga da IA generativa.
- ``LimiaresForm``: limites do motor de análise (nota, avaliações, fotos e
  meses sem atualização).

Rótulos, ajudas e mensagens vêm de ``apps/nucleo/textos.py``.
"""
from __future__ import annotations

import re

from django import forms

from apps.nucleo.textos import texto
from apps.prospeccao.models import (
    MODELO_IA_PADRAO,
    Busca,
    ConexaoGoogle,
    ConfiguracaoProspeccao,
)

# Chaves da API do Google: alfanuméricas com '-' e '_' (ex.: prefixo "AIza...").
_RE_CHAVE_API = re.compile(r"^[A-Za-z0-9_\-]+$")
_MIN_CHAVE = 20
_MAX_CHAVE = 200

# Chaves de outras APIs (ex.: Anthropic "sk-ant-..."): sem espaços/controles.
_RE_CHAVE_IA = re.compile(r"^[A-Za-z0-9_\-.]+$")
_MAX_CHAVE_IA = 400

# Identificador de modelo (ex.: "claude-opus-5-5").
_RE_MODELO = re.compile(r"^[a-z0-9][a-z0-9.\-]{2,79}$")

# Limites de raio aceitos pela Places API (metros).
RAIO_MINIMO = 1
RAIO_MAXIMO = 50_000

_T = "prospeccao.formularios."


def _validar_chave_google(chave: str) -> str:
    """Valida o formato da chave do Google sem registrar seu valor em log."""
    chave = (chave or "").strip()
    if not chave:
        raise forms.ValidationError(texto(_T + "erro_chave_obrigatoria"), code="obrigatorio")
    if not (_MIN_CHAVE <= len(chave) <= _MAX_CHAVE):
        raise forms.ValidationError(texto(_T + "erro_chave_tamanho"), code="tamanho")
    if not _RE_CHAVE_API.match(chave):
        raise forms.ValidationError(texto(_T + "erro_chave_formato"), code="formato")
    return chave


def _campo_senha(rotulo: str, ajuda: str, obrigatorio: bool, placeholder: str) -> forms.CharField:
    """Campo write-only (nunca reexibe o valor salvo)."""
    return forms.CharField(
        label=rotulo,
        required=obrigatorio,
        strip=True,
        help_text=ajuda,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "off", "placeholder": placeholder, "spellcheck": "false"},
        ),
    )


class ConexaoGoogleForm(forms.ModelForm):
    """Cria/edita uma ``ConexaoGoogle`` recebendo a chave de forma write-only."""

    chave_api = _campo_senha(
        texto(_T + "conexao_chave_rotulo"),
        texto(_T + "conexao_chave_ajuda"),
        True,
        "••••••••••••",
    )

    class Meta:
        model = ConexaoGoogle
        fields = ("nome", "ativo")

    def clean_chave_api(self) -> str:
        return _validar_chave_google(self.cleaned_data.get("chave_api"))

    def save(self, commit: bool = True) -> ConexaoGoogle:
        """Aplica a chave via a property (que cifra) antes de persistir."""
        conexao = super().save(commit=False)
        conexao.chave_api = self.cleaned_data["chave_api"]
        if commit:
            conexao.save()
        return conexao


class BuscaForm(forms.ModelForm):
    """Cria uma ``Busca`` com validação forte dos campos."""

    class Meta:
        model = Busca
        fields = ("conexao", "termo", "localizacao", "raio_metros")
        widgets = {
            "termo": forms.TextInput(attrs={"placeholder": texto(_T + "termo_placeholder")}),
            "localizacao": forms.TextInput(
                attrs={"placeholder": texto(_T + "localizacao_placeholder")}
            ),
            "raio_metros": forms.NumberInput(
                attrs={"min": RAIO_MINIMO, "max": RAIO_MAXIMO, "step": 100}
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Só conexões ativas podem ser usadas; sem conexão vale a chave do Painel.
        self.fields["conexao"].queryset = ConexaoGoogle.objects.filter(ativo=True)
        self.fields["conexao"].required = False
        self.fields["conexao"].empty_label = texto(_T + "busca_conexao_vazio")
        self.fields["conexao"].help_text = texto(_T + "busca_conexao_ajuda")

    def clean_termo(self) -> str:
        termo = (self.cleaned_data.get("termo") or "").strip()
        if len(termo) < 2:
            raise forms.ValidationError(texto(_T + "erro_termo_curto"), code="curto")
        return termo

    def clean_localizacao(self) -> str:
        localizacao = (self.cleaned_data.get("localizacao") or "").strip()
        if len(localizacao) < 2:
            raise forms.ValidationError(texto(_T + "erro_localizacao_curta"), code="curto")
        return localizacao

    def clean_raio_metros(self) -> int:
        raio = self.cleaned_data.get("raio_metros")
        if raio is None:
            raise forms.ValidationError(texto(_T + "erro_raio_obrigatorio"), code="obrigatorio")
        if not (RAIO_MINIMO <= raio <= RAIO_MAXIMO):
            raise forms.ValidationError(
                texto(_T + "erro_raio_intervalo", minimo=RAIO_MINIMO, maximo=RAIO_MAXIMO),
                code="intervalo",
            )
        return raio


class ChaveGoogleForm(forms.Form):
    """Campo do Painel para colar e salvar a chave da Google Places API (New)."""

    chave_google = forms.CharField()  # substituído em __init__ (placeholder dinâmico)

    def __init__(self, *args, configurada: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["chave_google"] = _campo_senha(
            texto(_T + "chave_google_rotulo"),
            texto(_T + "chave_google_ajuda"),
            True,
            texto(_T + ("chave_placeholder_configurada" if configurada else "chave_placeholder_vazia")),
        )

    def clean_chave_google(self) -> str:
        return _validar_chave_google(self.cleaned_data.get("chave_google"))

    def salvar(self, config: ConfiguracaoProspeccao) -> ConfiguracaoProspeccao:
        config.chave_google = self.cleaned_data["chave_google"]
        config.save()
        return config


class IAForm(forms.ModelForm):
    """Configuração da IA generativa (Claude): chave write-only, modelo e ativa."""

    ia_chave = forms.CharField(required=False)  # substituído em __init__

    class Meta:
        model = ConfiguracaoProspeccao
        fields = ("ia_modelo", "ia_ativa")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        configurada = bool(self.instance and self.instance.tem_ia_chave)
        self.fields["ia_chave"] = _campo_senha(
            texto(_T + "ia_chave_rotulo"),
            texto(_T + "ia_chave_ajuda"),
            False,
            texto(_T + ("chave_placeholder_configurada" if configurada else "chave_placeholder_vazia")),
        )
        self.fields["ia_modelo"].label = texto(_T + "ia_modelo_rotulo")
        self.fields["ia_modelo"].help_text = texto(_T + "ia_modelo_ajuda", modelo=MODELO_IA_PADRAO)
        self.fields["ia_modelo"].widget.attrs.update(
            {"placeholder": MODELO_IA_PADRAO, "spellcheck": "false", "autocomplete": "off"}
        )
        self.fields["ia_ativa"].label = texto(_T + "ia_ativa_rotulo")
        self.fields["ia_ativa"].help_text = texto(_T + "ia_ativa_ajuda")
        # Mantém a ordem: chave, modelo, ativa.
        self.order_fields(["ia_chave", "ia_modelo", "ia_ativa"])

    def clean_ia_chave(self) -> str:
        chave = (self.cleaned_data.get("ia_chave") or "").strip()
        if not chave:
            return ""
        if len(chave) > _MAX_CHAVE_IA or len(chave) < _MIN_CHAVE:
            raise forms.ValidationError(texto(_T + "erro_chave_tamanho"), code="tamanho")
        if not _RE_CHAVE_IA.match(chave):
            raise forms.ValidationError(texto(_T + "erro_chave_formato"), code="formato")
        return chave

    def clean_ia_modelo(self) -> str:
        modelo = (self.cleaned_data.get("ia_modelo") or "").strip().lower() or MODELO_IA_PADRAO
        if not _RE_MODELO.match(modelo):
            raise forms.ValidationError(
                texto(_T + "erro_modelo", modelo=MODELO_IA_PADRAO), code="modelo"
            )
        return modelo

    def save(self, commit: bool = True) -> ConfiguracaoProspeccao:
        """Chave em branco mantém a atual; uma nova chave é cifrada."""
        config = super().save(commit=False)
        nova_chave = self.cleaned_data.get("ia_chave")
        if nova_chave:
            config.ia_chave = nova_chave
        if commit:
            config.save()
        return config


class LimiaresForm(forms.ModelForm):
    """Limites do motor de análise dos perfis do Google."""

    class Meta:
        model = ConfiguracaoProspeccao
        fields = ("limiar_nota", "limiar_avaliacoes", "limiar_fotos", "limiar_meses")
        widgets = {
            "limiar_nota": forms.NumberInput(attrs={"min": 0, "max": 5, "step": "0.1"}),
            "limiar_avaliacoes": forms.NumberInput(attrs={"min": 0, "max": 100000, "step": 1}),
            "limiar_fotos": forms.NumberInput(attrs={"min": 0, "max": 10, "step": 1}),
            "limiar_meses": forms.NumberInput(attrs={"min": 1, "max": 60, "step": 1}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for campo, chave in (
            ("limiar_nota", "limiar_nota"),
            ("limiar_avaliacoes", "limiar_avaliacoes"),
            ("limiar_fotos", "limiar_fotos"),
            ("limiar_meses", "limiar_meses"),
        ):
            self.fields[campo].label = texto(f"{_T}{chave}_rotulo")
            self.fields[campo].help_text = texto(f"{_T}{chave}_ajuda")

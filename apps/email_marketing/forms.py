"""Formulários do módulo de Marketing por E-mail (adendo 3 — MÓDULO 5).

- ``ConfiguracaoEnvioForm``: cria/edita uma ``ConfiguracaoEnvio``. A senha SMTP
  chega por um campo WRITE-ONLY e é persistida cifrada (via a property ``senha``
  do modelo). Ao EDITAR, deixá-la em branco MANTÉM a senha atual. TLS e SSL não
  podem ser ambos ativados; no tipo SMTP, host e e-mail remetente são exigidos.
- ``CampanhaForm``: cria/edita uma ``Campanha`` (assunto, corpos, configuração e
  lista opcional).
- ``ContatoImportacaoForm``: importa contatos em massa a partir de um textarea
  (um por linha, aceitando ``"Nome <email>"``), validando linha a linha.
- ``ListaForm``: cria/edita uma ``Lista`` com seleção múltipla de contatos.
"""
from __future__ import annotations

from email.utils import parseaddr

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from apps.email_marketing.models import (
    Campanha,
    ConfiguracaoEnvio,
    Contato,
    Lista,
    TemplateEmail,
)

PORTA_MINIMA = 1
PORTA_MAXIMA = 65535


class TemplateEmailForm(forms.ModelForm):
    """Cria/edita um ``TemplateEmail`` (modelo de e-mail reutilizável)."""

    class Meta:
        model = TemplateEmail
        fields = ("nome", "descricao", "categoria", "corpo_html", "corpo_texto", "ativo")
        widgets = {
            "nome": forms.TextInput(attrs={"class": "campo", "placeholder": _("Ex.: Newsletter mensal")}),
            "descricao": forms.TextInput(attrs={"class": "campo", "placeholder": _("Descrição curta")}),
            "categoria": forms.Select(attrs={"class": "campo"}),
            "corpo_html": forms.Textarea(
                attrs={"class": "campo", "rows": 16, "spellcheck": "false"}
            ),
            "corpo_texto": forms.Textarea(attrs={"class": "campo", "rows": 6}),
        }

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 2:
            raise forms.ValidationError(_("O nome deve ter ao menos 2 caracteres."), code="curto")
        return nome

    def clean_corpo_html(self) -> str:
        corpo = self.cleaned_data.get("corpo_html") or ""
        if not corpo.strip():
            raise forms.ValidationError(_("Informe o corpo (HTML) do modelo."), code="obrigatorio")
        return corpo


class ConfiguracaoEnvioForm(forms.ModelForm):
    """Cria/edita uma ``ConfiguracaoEnvio`` recebendo a senha de forma write-only."""

    senha = forms.CharField(
        label=_("Senha SMTP"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": "••••••••"},
        ),
        help_text=_("Usada quando o tipo é SMTP. Em branco ao editar = manter."),
    )

    class Meta:
        model = ConfiguracaoEnvio
        fields = (
            "nome",
            "tipo",
            "email_remetente",
            "nome_remetente",
            "responder_para",
            "host",
            "porta",
            "usuario",
            "usar_tls",
            "usar_ssl",
            "ativo",
        )
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: Remetente principal")}),
            "tipo": forms.Select(attrs={"data-tipo-envio": "true"}),
            "email_remetente": forms.EmailInput(attrs={"placeholder": "no-reply@empresa.com.br"}),
            "nome_remetente": forms.TextInput(attrs={"placeholder": _("Ex.: Equipe modulos")}),
            "responder_para": forms.EmailInput(attrs={"placeholder": "contato@empresa.com.br"}),
            "host": forms.TextInput(attrs={"placeholder": _("Ex.: smtp.empresa.com.br")}),
            "porta": forms.NumberInput(attrs={"min": PORTA_MINIMA, "max": PORTA_MAXIMA, "step": 1}),
            "usuario": forms.TextInput(attrs={"autocomplete": "off", "placeholder": _("usuário SMTP")}),
        }

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if not nome:
            raise forms.ValidationError(_("Informe um nome para a configuração."), code="obrigatorio")
        return nome

    def clean_porta(self) -> int:
        porta = self.cleaned_data.get("porta")
        if porta is None:
            raise forms.ValidationError(_("Informe a porta."), code="obrigatorio")
        if not (PORTA_MINIMA <= porta <= PORTA_MAXIMA):
            raise forms.ValidationError(
                _("A porta deve estar entre %(min)d e %(max)d.")
                % {"min": PORTA_MINIMA, "max": PORTA_MAXIMA},
                code="intervalo",
            )
        return porta

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo")
        usar_tls = dados.get("usar_tls")
        usar_ssl = dados.get("usar_ssl")

        # TLS e SSL são mutuamente exclusivos.
        if usar_tls and usar_ssl:
            raise forms.ValidationError(
                _("Escolha TLS OU SSL, não ambos."), code="tls_ssl"
            )

        # No tipo SMTP, host e e-mail remetente são obrigatórios. Os guardas por
        # ``self.errors`` evitam erro duplicado quando o campo já falhou sozinho.
        if tipo == ConfiguracaoEnvio.Tipo.SMTP:
            if "host" not in self.errors and not (dados.get("host") or "").strip():
                self.add_error("host", _("Informe o host SMTP para o tipo SMTP."))
            if "email_remetente" not in self.errors and not (dados.get("email_remetente") or "").strip():
                self.add_error("email_remetente", _("Informe o e-mail remetente."))
        return dados

    def save(self, commit: bool = True) -> ConfiguracaoEnvio:
        """Aplica a senha via a property (que cifra) apenas se preenchida."""
        configuracao = super().save(commit=False)

        senha = self.cleaned_data.get("senha") or ""
        # Em branco = manter a senha existente (não apaga ao editar).
        if senha.strip():
            configuracao.senha = senha

        if commit:
            configuracao.save()
        return configuracao


class CampanhaForm(forms.ModelForm):
    """Cria/edita uma ``Campanha`` (corpos em textarea; lista opcional)."""

    class Meta:
        model = Campanha
        fields = ("nome", "assunto", "corpo_html", "corpo_texto", "configuracao", "lista")
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: Novidades de agosto")}),
            "assunto": forms.TextInput(
                attrs={"placeholder": _("Ex.: {{ nome }}, temos novidades para você")}
            ),
            "corpo_html": forms.Textarea(
                attrs={
                    "rows": 12,
                    "spellcheck": "false",
                    "placeholder": "<p>Olá, {{ nome }}!</p>",
                }
            ),
            "corpo_texto": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": _("Versão em texto puro (opcional; derivada do HTML se vazia)."),
                }
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Só configurações ativas podem ser usadas em uma campanha.
        self.fields["configuracao"].queryset = ConfiguracaoEnvio.objects.filter(ativo=True)
        self.fields["configuracao"].empty_label = _("Selecione uma configuração de envio")
        self.fields["lista"].queryset = Lista.objects.all()
        self.fields["lista"].required = False
        self.fields["lista"].empty_label = _("Todos os contatos inscritos")

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 2:
            raise forms.ValidationError(_("O nome deve ter ao menos 2 caracteres."), code="curto")
        return nome

    def clean_assunto(self) -> str:
        assunto = (self.cleaned_data.get("assunto") or "").strip()
        if not assunto:
            raise forms.ValidationError(_("Informe o assunto da campanha."), code="obrigatorio")
        return assunto

    def clean_corpo_html(self) -> str:
        corpo = self.cleaned_data.get("corpo_html") or ""
        if not corpo.strip():
            raise forms.ValidationError(_("Informe o corpo (HTML) da campanha."), code="obrigatorio")
        return corpo


class ContatoImportacaoForm(forms.Form):
    """Importa contatos em massa a partir de um textarea (um e-mail por linha)."""

    emails = forms.CharField(
        label=_("E-mails"),
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "placeholder": "maria@empresa.com.br\nJoão Silva <joao@empresa.com.br>",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
        help_text=_("Um por linha. Aceita \"Nome <email>\". E-mails inválidos são ignorados."),
    )

    def clean_emails(self) -> str:
        """Valida cada linha; expõe ``entradas_validas`` e ``linhas_invalidas``."""
        bruto = self.cleaned_data.get("emails") or ""
        entradas: list[tuple[str, str]] = []
        invalidas: list[str] = []
        vistos: set[str] = set()

        for linha in bruto.splitlines():
            linha = linha.strip()
            if not linha:
                continue
            nome, email = parseaddr(linha)
            nome = (nome or "").strip()
            email = (email or "").strip().lower()
            try:
                validate_email(email)
            except ValidationError:
                invalidas.append(linha)
                continue
            if email in vistos:
                continue  # ignora duplicatas dentro do próprio textarea
            vistos.add(email)
            entradas.append((nome, email))

        if not entradas:
            raise forms.ValidationError(
                _("Nenhum e-mail válido foi encontrado."), code="vazio"
            )

        self.entradas_validas = entradas
        self.linhas_invalidas = invalidas
        return bruto


class ListaForm(forms.ModelForm):
    """Cria/edita uma ``Lista`` com seleção múltipla de contatos."""

    contatos = forms.ModelMultipleChoiceField(
        label=_("Contatos"),
        queryset=Contato.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 10}),
        help_text=_("Selecione os contatos que farão parte desta lista."),
    )

    class Meta:
        model = Lista
        fields = ("nome", "descricao", "contatos")
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": _("Ex.: Clientes ativos")}),
            "descricao": forms.Textarea(attrs={"rows": 3, "placeholder": _("Descrição opcional")}),
        }

    def clean_nome(self) -> str:
        nome = (self.cleaned_data.get("nome") or "").strip()
        if len(nome) < 2:
            raise forms.ValidationError(_("O nome deve ter ao menos 2 caracteres."), code="curto")
        return nome

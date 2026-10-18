"""Registro do módulo de Marketing por E-mail no núcleo (adendo 3 — MÓDULO 5).

Define ``ModuloEmailMarketing`` (subclasse de ``ModuloBase``) e a registra no
``registro`` singleton. Fornece:

- ``itens_menu``: os itens de sidebar "Campanhas", "Contatos" e "Configurações
  de envio".
- ``cards_resumo``: 3 KPIs (Campanhas enviadas / Contatos inscritos / E-mails
  enviados) a partir do banco.
- ``contexto_dashboard``: ``{}`` (o painel principal é da prospecção).
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.email_marketing.modulo")


@registro.registrar
class ModuloEmailMarketing(ModuloBase):
    """Módulo de marketing por e-mail: campanhas em massa por remetente próprio."""

    slug = "email_marketing"
    nome = texto("modulos.email_marketing.nome")
    icone = "megafone"
    ordem = 60
    descricao = texto("modulos.email_marketing.descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para a lista de campanhas."""
        return "email_marketing:campanhas"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        rotas_campanhas = {
            "email_marketing:campanhas",
            "email_marketing:campanha_nova",
            "email_marketing:campanha_detalhe",
            "email_marketing:campanha_enviar",
        }
        rotas_contatos = {"email_marketing:contatos", "email_marketing:listas"}
        rotas_config = {"email_marketing:configuracoes", "email_marketing:config_testar"}
        rotas_templates = {
            "email_marketing:templates",
            "email_marketing:template_editar",
        }
        return [
            {
                "rotulo": texto("modulos.email_marketing.menu.campanhas"),
                "url": self._url_ou_hash("email_marketing:campanhas"),
                "icone": "megafone",
                "ativo": rota_atual in rotas_campanhas,
            },
            {
                "rotulo": texto("modulos.email_marketing.menu.modelos"),
                "url": self._url_ou_hash("email_marketing:templates"),
                "icone": "editar",
                "ativo": rota_atual in rotas_templates,
            },
            {
                "rotulo": texto("modulos.email_marketing.menu.contatos"),
                "url": self._url_ou_hash("email_marketing:contatos"),
                "icone": "grupo",
                "ativo": rota_atual in rotas_contatos,
            },
            {
                "rotulo": texto("modulos.email_marketing.menu.configuracoes"),
                "url": self._url_ou_hash("email_marketing:configuracoes"),
                "icone": "config",
                "ativo": rota_atual in rotas_config,
            },
        ]

    def cards_resumo(self, request) -> list[dict]:
        """KPIs do marketing por e-mail para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from apps.email_marketing.models import Campanha, Contato, EnvioEmail

            campanhas_enviadas = Campanha.objects.filter(
                status__in=[Campanha.Status.ENVIADA, Campanha.Status.PARCIAL]
            ).count()
            contatos_inscritos = Contato.objects.filter(inscrito=True).count()
            emails_enviados = EnvioEmail.objects.filter(
                status=EnvioEmail.Status.ENVIADO
            ).count()

            url_campanhas = self._url_ou_hash("email_marketing:campanhas")
            url_contatos = self._url_ou_hash("email_marketing:contatos")
            return [
                {
                    "rotulo": texto("modulos.email_marketing.cards.campanhas_rotulo"),
                    "valor": campanhas_enviadas,
                    "detalhe": texto("modulos.email_marketing.cards.campanhas_detalhe"),
                    "icone": "megafone",
                    "cor": "#7c5cff",
                    "url": url_campanhas,
                },
                {
                    "rotulo": texto("modulos.email_marketing.cards.contatos_rotulo"),
                    "valor": contatos_inscritos,
                    "detalhe": texto("modulos.email_marketing.cards.contatos_detalhe"),
                    "icone": "grupo",
                    "cor": "#34d399",
                    "url": url_contatos,
                },
                {
                    "rotulo": texto("modulos.email_marketing.cards.emails_rotulo"),
                    "valor": emails_enviados,
                    "detalhe": texto("modulos.email_marketing.cards.emails_detalhe"),
                    "icone": "enviar",
                    "cor": "#38bdf8",
                    "url": url_campanhas,
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo do marketing por e-mail.")
            return []

    def contexto_dashboard(self, request) -> dict:
        """O painel principal é da prospecção; este módulo não injeta dados."""
        return {}

    def excluir_dados(self, request) -> int:
        """Exclui os DADOS OPERACIONAIS do módulo (campanhas, envios, contatos,
        listas). Preserva a configuração de envio (remetente/SMTP) e a biblioteca
        de modelos, que são configuração, não dados de operação.
        """
        try:
            from apps.email_marketing.models import (
                Campanha,
                Contato,
                EnvioEmail,
                Lista,
            )

            total = 0
            total += EnvioEmail.objects.all().delete()[0]
            total += Campanha.objects.all().delete()[0]
            total += Lista.objects.all().delete()[0]
            total += Contato.objects.all().delete()[0]
            return total
        except Exception:  # pragma: no cover - resiliência
            logger.exception("Falha ao excluir dados do e-mail marketing.")
            return 0

    # -- Auxiliares de menu -------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            logger.debug("URL '%s' não pôde ser resolvida.", nome_url)
            return "#"

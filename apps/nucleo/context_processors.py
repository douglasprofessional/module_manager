"""Context processor de navegação e marca (seção 5 da SPEC).

Injeta em TODOS os templates: nome e logo do sistema (marca branca), tema
atual, itens/seções de menu dos módulos HABILITADOS, o menu de Configurações
Gerais (Perfil/Configurações), o menu da conta (Sair) e a rota atual.

Resiliência é requisito: qualquer falha aqui degrada para defaults seguros
para nunca quebrar a renderização de uma página.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from .models import ConfiguracaoSistema, ModuloEstado, Tema
from .modulos import registro
from .textos import texto

logger = logging.getLogger("modulos.nucleo.context_processors")

# Nome de fallback caso o singleton ainda não exista (ex.: durante o migrate).
SITE_NOME_PADRAO = texto("geral.nome_padrao")


def _url_ou_hash(nome_url: str) -> str:
    """Resolve um name de URL; retorna ``"#"`` se não for resolvível."""
    if not nome_url:
        return "#"
    try:
        return reverse(nome_url)
    except NoReverseMatch:
        return "#"


def _rota_atual(request) -> str:
    """Nome da view atual (ex.: ``"nucleo:dashboard"``) ou ``""``."""
    match = getattr(request, "resolver_match", None)
    if not match:
        return ""
    return getattr(match, "view_name", "") or ""


def _menu_geral(rota_atual: str) -> list[dict]:
    """Seção fixa "Configurações Gerais do Sistema" (sempre visível)."""
    return [
        {
            "rotulo": texto("menu.meu_perfil"),
            "url": _url_ou_hash("contas:perfil"),
            "icone": "perfil",
            "ativo": rota_atual == "contas:perfil",
        },
        {
            "rotulo": texto("menu.configuracoes"),
            "url": _url_ou_hash("nucleo:configuracoes"),
            "icone": "config",
            "ativo": rota_atual.startswith("nucleo:config"),
        },
    ]


def _menu_conta(rota_atual: str) -> list[dict]:
    """Menu da conta (apenas Sair; Perfil/Config estão em Configurações Gerais)."""
    return [
        {
            "rotulo": texto("menu.sair"),
            "url": _url_ou_hash("contas:logout"),
            "icone": "sair",
            "ativo": False,
        },
    ]


def _inatividade_segundos() -> int:
    """Janela de inatividade (segundos) usada pelo logout automático no navegador."""
    try:
        return int(getattr(settings, "SESSAO_INATIVIDADE_SEGUNDOS", 600))
    except (TypeError, ValueError):
        return 600


def _tema_atual(request, config) -> str:
    """Tema efetivo: preferência do usuário logado ou o padrão do sistema."""
    usuario = getattr(request, "user", None)
    if usuario is not None and getattr(usuario, "is_authenticated", False):
        tema = getattr(usuario, "tema", "") or ""
        if tema in (Tema.CLARO, Tema.ESCURO):
            return tema
    return getattr(config, "tema_padrao", Tema.CLARO) or Tema.CLARO


def navegacao(request) -> dict:
    """Retorna o contexto de navegação/marca para os templates.

    Em caso de erro, devolve defaults seguros para não interromper o render.
    """
    try:
        config = ConfiguracaoSistema.obter()
        rota_atual = _rota_atual(request)
        slugs = ModuloEstado.slugs_habilitados()
        logo = getattr(config, "logo", None)
        try:
            logo_url = logo.url if logo else ""
        except Exception:
            logo_url = ""
        return {
            "site_nome": getattr(config, "nome_sistema", SITE_NOME_PADRAO) or SITE_NOME_PADRAO,
            "site_logo_url": logo_url,
            "tema_atual": _tema_atual(request, config),
            "modulos_menu": registro.itens_menu(request, slugs),
            "modulos_secoes": registro.secoes_menu(request, slugs),
            "menu_geral": _menu_geral(rota_atual),
            "menu_conta": _menu_conta(rota_atual),
            "rota_atual": rota_atual,
            "sessao_inatividade_segundos": _inatividade_segundos(),
            "url_login": _url_ou_hash("contas:login"),
        }
    except Exception:  # pragma: no cover - proteção defensiva do render
        logger.exception("Falha ao montar a navegação; usando defaults seguros.")
        return {
            "site_nome": SITE_NOME_PADRAO,
            "site_logo_url": "",
            "tema_atual": Tema.CLARO,
            "modulos_menu": [],
            "modulos_secoes": [],
            "menu_geral": [],
            "menu_conta": [],
            "rota_atual": "",
            "sessao_inatividade_segundos": _inatividade_segundos(),
            "url_login": "",
        }

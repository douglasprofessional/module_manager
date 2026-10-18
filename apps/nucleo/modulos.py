"""Registro de módulos — o coração da BASE (seção 6 da SPEC).

Este módulo define o contrato de extensão do sistema:

- ``ModuloBase``: classe-base que cada app-módulo estende para se anunciar ao
  núcleo (item de menu na sidebar e dados para o painel do dashboard).
- ``RegistroModulos``: coleção ordenada de módulos registrados.
- ``registro``: instância singleton usada por todos (context processor e view
  do dashboard) e pelo ``ready()`` de cada app-módulo para se registrar.

O núcleo NUNCA importa os apps-módulo: a descoberta é invertida — cada módulo
importa este arquivo e chama ``registro.registrar(...)`` no seu ``ready()``.
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

logger = logging.getLogger("modulos.nucleo.modulos")


class ModuloBase:
    """Contrato que cada módulo implementa para aparecer no sistema.

    Atributos de classe (sobrescrever no módulo concreto):
        slug: identificador curto e único do módulo (ex.: ``"prospeccao"``).
        nome: rótulo exibido no menu (ex.: ``"Prospecção"``).
        icone: chave de ícone da sidebar (ver seção 5 da SPEC).
        ordem: peso de ordenação (menor aparece primeiro). Padrão 100.
        descricao: texto curto opcional.

    Métodos (todos opcionais de sobrescrever):
        url_inicial: name de URL do item principal do módulo.
        itens_menu: lista de ``ItemMenu`` (dicts) que o módulo adiciona à sidebar.
        contexto_dashboard: dados que o módulo injeta no painel (seção 7).
    """

    slug: str = ""
    nome: str = ""
    icone: str = "dashboard"
    ordem: int = 100
    descricao: str = ""

    def url_inicial(self) -> str:
        """Retorna o *name* de URL do item principal. Padrão: ``"#"``."""
        return "#"

    def itens_menu(self, request) -> list[dict]:
        """Retorna os ``ItemMenu`` do módulo para a sidebar.

        Implementação padrão: um único item apontando para ``url_inicial()``,
        marcado como ativo quando a rota atual pertence ao mesmo namespace.
        Cada item segue as chaves EXATAS da seção 5:
        ``{"rotulo", "url", "icone", "ativo"}``.
        """
        nome_url = self.url_inicial()
        url = "#"
        if nome_url and nome_url != "#":
            try:
                url = reverse(nome_url)
            except NoReverseMatch:
                logger.debug("URL '%s' do módulo '%s' não pôde ser resolvida.", nome_url, self.slug)
                url = "#"
        return [
            {
                "rotulo": self.nome,
                "url": url,
                "icone": self.icone,
                "ativo": self._esta_ativo(request, nome_url),
            }
        ]

    def contexto_dashboard(self, request) -> dict:
        """Dados que o módulo injeta no painel do dashboard. Padrão: ``{}``."""
        return {}

    def excluir_dados(self, request) -> int:
        """Exclui TODOS os dados deste módulo e retorna a contagem removida.

        Padrão: ``0`` (nada a excluir). Sobrescreva no módulo concreto para
        apagar seus próprios registros. Desabilitar um módulo NÃO apaga dados;
        apenas esta ação (explícita, no painel de Configurações) o faz.
        """
        return 0

    def suporta_exclusao(self) -> bool:
        """Indica se o módulo implementa ``excluir_dados`` (para exibir o botão)."""
        return type(self).excluir_dados is not ModuloBase.excluir_dados

    def cards_resumo(self, request) -> list[dict]:
        """Cards de KPI que o módulo exibe no topo do dashboard. Padrão: ``[]``.

        Cada card é um dict com as chaves EXATAS::

            {
                "rotulo": str,      # ex.: "Chamados abertos"
                "valor": str | int, # ex.: 8
                "detalhe": str,     # ex.: "2 em risco" (opcional)
                "icone": str,       # chave de ícone (ver _icones.html)
                "cor": str,         # "#hex" do quadradinho do ícone
                "url": str,         # URL já resolvida ou "#"
                "modulo": str,      # slug do módulo (preenchido pelo registro)
            }

        Este é o ponto de harmonia entre módulos: qualquer módulo (Kanban, SLA,
        Prospecção…) publica seus indicadores no mesmo formato e o dashboard os
        renderiza de modo uniforme, sem o núcleo conhecer cada domínio.
        """
        return []

    def _esta_ativo(self, request, nome_url: str) -> bool:
        """Marca o item como ativo quando a rota atual compartilha o namespace."""
        match = getattr(request, "resolver_match", None)
        if not match or not nome_url or ":" not in nome_url:
            return False
        namespace_alvo = nome_url.split(":", 1)[0]
        atual = getattr(match, "view_name", "") or ""
        return atual.split(":", 1)[0] == namespace_alvo


class RegistroModulos:
    """Coleção de módulos registrados, indexada por ``slug``.

    É idempotente: registrar o mesmo ``slug`` novamente substitui a entrada
    anterior (evita duplicação caso ``ready()`` rode mais de uma vez).
    """

    def __init__(self) -> None:
        self._modulos: dict[str, ModuloBase] = {}

    def registrar(self, classe_modulo: type[ModuloBase]) -> type[ModuloBase]:
        """Registra uma subclasse de ``ModuloBase`` e retorna a própria classe.

        Amigável a decorator::

            @registro.registrar
            class MeuModulo(ModuloBase):
                slug = "meu"
        """
        instancia = classe_modulo()
        slug = getattr(instancia, "slug", "") or classe_modulo.__name__
        if slug in self._modulos:
            logger.debug("Módulo '%s' re-registrado; substituindo entrada anterior.", slug)
        self._modulos[slug] = instancia
        logger.info("Módulo registrado: %s (%s).", slug, instancia.nome or classe_modulo.__name__)
        return classe_modulo

    def todos(self) -> list[ModuloBase]:
        """Retorna os módulos ordenados por ``ordem`` e depois por ``nome``."""
        return sorted(self._modulos.values(), key=lambda m: (m.ordem, (m.nome or "").lower()))

    def obter(self, slug: str) -> ModuloBase | None:
        """Retorna a instância do módulo pelo ``slug`` (ou ``None``)."""
        return self._modulos.get(slug)

    def _selecionados(self, slugs: set[str] | None) -> list[ModuloBase]:
        """Módulos na ordem canônica, filtrados por ``slugs`` quando informado.

        ``slugs=None`` significa "todos" (retrocompatível). Passe o conjunto de
        slugs HABILITADOS para respeitar o liga/desliga de módulos.
        """
        todos = self.todos()
        if slugs is None:
            return todos
        return [m for m in todos if getattr(m, "slug", "") in slugs]

    def itens_menu(self, request, slugs: set[str] | None = None) -> list[dict]:
        """Concatena os ``itens_menu`` dos módulos (habilitados, se ``slugs``).

        Resiliente: falha de um módulo não derruba o menu inteiro.
        """
        itens: list[dict] = []
        for modulo in self._selecionados(slugs):
            try:
                itens.extend(modulo.itens_menu(request) or [])
            except Exception:  # pragma: no cover - proteção defensiva do render
                logger.exception("Falha ao montar itens_menu do módulo '%s'.", getattr(modulo, "slug", "?"))
        return itens

    def secoes_menu(self, request, slugs: set[str] | None = None) -> list[dict]:
        """Agrupa os itens de menu por módulo (para dividir a sidebar por seções).

        Cada seção: ``{"slug", "nome", "icone", "itens": [ItemMenu, ...]}``.
        Módulos sem itens são omitidos. Respeita o filtro de habilitados.
        """
        secoes: list[dict] = []
        for modulo in self._selecionados(slugs):
            try:
                itens = modulo.itens_menu(request) or []
            except Exception:  # pragma: no cover - proteção defensiva do render
                logger.exception("Falha ao montar seção do módulo '%s'.", getattr(modulo, "slug", "?"))
                itens = []
            if not itens:
                continue
            secoes.append(
                {
                    "slug": getattr(modulo, "slug", ""),
                    "nome": getattr(modulo, "nome", "") or getattr(modulo, "slug", ""),
                    "icone": getattr(modulo, "icone", "dashboard"),
                    "itens": itens,
                }
            )
        return secoes

    def contexto_dashboard(self, request, slugs: set[str] | None = None) -> dict:
        """Faz o merge raso dos ``contexto_dashboard`` dos módulos (habilitados).

        A ordem canônica define a precedência (módulos posteriores sobrescrevem
        chaves iguais). Resiliente: exceção em um módulo é registrada e ignorada.
        """
        contexto: dict = {}
        for modulo in self._selecionados(slugs):
            try:
                dados = modulo.contexto_dashboard(request) or {}
                if isinstance(dados, dict):
                    contexto.update(dados)
            except Exception:  # pragma: no cover - proteção defensiva do dashboard
                logger.exception("Falha em contexto_dashboard do módulo '%s'.", getattr(modulo, "slug", "?"))
        return contexto

    def cards_resumo(self, request, slugs: set[str] | None = None) -> list[dict]:
        """Concatena os ``cards_resumo`` de todos os módulos (ordem canônica).

        Anexa a cada card o ``slug`` do módulo de origem (se ausente) e é
        resiliente: a falha de um módulo não derruba a faixa de KPIs.
        """
        cards: list[dict] = []
        for modulo in self._selecionados(slugs):
            try:
                for card in modulo.cards_resumo(request) or []:
                    if isinstance(card, dict):
                        card.setdefault("modulo", getattr(modulo, "slug", ""))
                        cards.append(card)
            except Exception:  # pragma: no cover - proteção defensiva do dashboard
                logger.exception("Falha em cards_resumo do módulo '%s'.", getattr(modulo, "slug", "?"))
        return cards


# Singleton usado por todo o sistema. É o ÚNICO ponto de extensão do núcleo.
registro = RegistroModulos()

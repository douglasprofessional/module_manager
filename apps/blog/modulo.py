"""Registro do módulo Blog no núcleo (seções 6 e 7 da SPEC).

Define ``ModuloBlog`` (subclasse de ``ModuloBase``) e a registra no ``registro``
singleton. Fornece:

- ``itens_menu``: itens de sidebar do módulo (Posts, Novo post, Categorias, Tags).
- ``cards_resumo``: 3 KPIs (Publicados, Rascunhos, Agendados) para a faixa do topo.
- ``contexto_dashboard``: chaves com prefixo ``blog_`` (ou ``{}`` em caso de falha).
- ``excluir_dados``: apaga Post, Tag e Category (retorna a contagem total).

Tudo é resiliente: qualquer falha degrada para vazio/zero sem derrubar o núcleo.
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.blog.modulo")


@registro.registrar
class ModuloBlog(ModuloBase):
    """Módulo de conteúdo: posts, categorias e tags com validação SEO/GEO/A11y."""

    slug = "blog"
    nome = texto("modulos.blog.nome")
    icone = "blog"
    ordem = 50
    descricao = texto("modulos.blog.descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para a lista de posts."""
        return "blog:lista"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        definicoes = [
            (
                texto("modulos.blog.menu.posts"),
                "blog:lista",
                "blog",
                {"blog:lista", "blog:post_edit", "blog:post_delete"},
            ),
            (texto("modulos.blog.menu.novo_post"), "blog:post_create", "mais", {"blog:post_create"}),
            (
                texto("modulos.blog.menu.categorias"),
                "blog:category_list",
                "categoria",
                {
                    "blog:category_list",
                    "blog:category_create",
                    "blog:category_edit",
                    "blog:category_delete",
                },
            ),
            (
                texto("modulos.blog.menu.tags"),
                "blog:tag_list",
                "tag",
                {"blog:tag_list", "blog:tag_create", "blog:tag_edit", "blog:tag_delete"},
            ),
        ]
        itens: list[dict] = []
        for rotulo, nome_url, icone, rotas_ativas in definicoes:
            itens.append(
                {
                    "rotulo": rotulo,
                    "url": self._url_ou_hash(nome_url),
                    "icone": icone,
                    "ativo": rota_atual in rotas_ativas,
                }
            )
        return itens

    def cards_resumo(self, request) -> list[dict]:
        """KPIs do blog para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from django.db.models import Count, Q

            from apps.blog.models import Post

            contagem = Post.objects.aggregate(
                publicados=Count("id", filter=Q(status=Post.Status.PUBLISHED)),
                rascunhos=Count("id", filter=Q(status=Post.Status.DRAFT)),
                agendados=Count("id", filter=Q(status=Post.Status.SCHEDULED)),
            )
            return [
                {
                    "rotulo": texto("modulos.blog.cards.publicados_rotulo"),
                    "valor": contagem["publicados"] or 0,
                    "detalhe": texto("modulos.blog.cards.publicados_detalhe"),
                    "icone": "post",
                    "cor": "#34d399",
                    "url": self._url_filtrada("published"),
                },
                {
                    "rotulo": texto("modulos.blog.cards.rascunhos_rotulo"),
                    "valor": contagem["rascunhos"] or 0,
                    "detalhe": texto("modulos.blog.cards.rascunhos_detalhe"),
                    "icone": "editar",
                    "cor": "#fbbf24",
                    "url": self._url_filtrada("draft"),
                },
                {
                    "rotulo": texto("modulos.blog.cards.agendados_rotulo"),
                    "valor": contagem["agendados"] or 0,
                    "detalhe": texto("modulos.blog.cards.agendados_detalhe"),
                    "icone": "calendario",
                    "cor": "#38bdf8",
                    "url": self._url_filtrada("scheduled"),
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo do blog.")
            return []

    def contexto_dashboard(self, request) -> dict:
        """Chaves (com prefixo ``blog_``) que o módulo injeta no painel.

        Resiliente: qualquer exceção resulta em ``{}`` (o núcleo segue com os
        seus defaults).
        """
        try:
            from django.db.models import Count, Q

            from apps.blog.models import Category, Post, Tag

            contagem = Post.objects.aggregate(
                total=Count("id"),
                publicados=Count("id", filter=Q(status=Post.Status.PUBLISHED)),
                rascunhos=Count("id", filter=Q(status=Post.Status.DRAFT)),
                agendados=Count("id", filter=Q(status=Post.Status.SCHEDULED)),
            )
            return {
                "blog_total_posts": contagem["total"] or 0,
                "blog_publicados": contagem["publicados"] or 0,
                "blog_rascunhos": contagem["rascunhos"] or 0,
                "blog_agendados": contagem["agendados"] or 0,
                "blog_total_categorias": Category.objects.count(),
                "blog_total_tags": Tag.objects.count(),
            }
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar contexto_dashboard do blog.")
            return {}

    def excluir_dados(self, request) -> int:
        """Apaga TODOS os dados do blog (Post, Tag, Category) e devolve o total.

        A ordem (posts primeiro) evita surpresas com as relações M2M. Retorna a
        soma de linhas efetivamente removidas dos três modelos.
        """
        from apps.blog.models import Category, Post, Tag

        total = 0
        for modelo in (Post, Tag, Category):
            apagados, _detalhe = modelo.objects.all().delete()
            total += apagados
        return total

    # -- Auxiliares ---------------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            logger.debug("URL '%s' não pôde ser resolvida.", nome_url)
            return "#"

    def _url_filtrada(self, status: str) -> str:
        """URL da lista de posts já filtrada por ``status`` (ou ``#``)."""
        base = self._url_ou_hash("blog:lista")
        if base == "#":
            return base
        return f"{base}?status={status}"

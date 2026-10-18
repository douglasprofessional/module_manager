"""Comando ``seed_blog``: popula conteúdo de demonstração do blog.

Cria algumas categorias e tags e ~3 posts (um publicado, um rascunho e um
agendado), com autor = primeiro superusuário/staff existente (ou ``None``, pois
o FK é opcional). Roda a validação SEO/GEO/A11y em cada post para preencher as
pontuações. NÃO cria papéis, usuários, itens de menu ou configurações do site.

Idempotente: reexecutar NÃO duplica. Categorias/tags são chaveadas pelo slug e
os posts pelo slug (``get_or_create``).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

CATEGORIAS_DEMO = [
    ("Tecnologia", "Artigos técnicos e tutoriais de desenvolvimento."),
    ("Marketing", "Conteúdo sobre presença digital e aquisição."),
]

TAGS_DEMO = ["django", "seo", "web", "geo"]

CONTEUDO_PUBLICADO = """
<p>Otimizar um blog para SEO e para os mecanismos generativos (GEO) exige
atenção a estrutura, clareza e dados verificáveis. Neste guia respondemos, de
forma direta, o que realmente move o ponteiro em 2026 e como aplicar cada ponto
no seu conteúdo com exemplos práticos.</p>
<h2>Como estruturar um artigo para SEO?</h2>
<p>Use títulos hierárquicos (H2, H3), parágrafos curtos e uma palavra-chave foco
bem definida. A meta description deve resumir a resposta em 120 a 160 caracteres.</p>
<ul>
  <li>Responda à intenção do leitor logo no primeiro parágrafo.</li>
  <li>Inclua listas e tabelas para facilitar a extração por IAs.</li>
  <li>Cite fontes externas confiáveis para reforçar a autoridade.</li>
</ul>
<h3>O que é GEO?</h3>
<p>GEO (Generative Engine Optimization) é otimizar o conteúdo para ser citado
por assistentes de IA. Segundo estimativas de mercado, mais de 60% das buscas já
passam por alguma camada generativa, o que torna respostas objetivas essenciais.</p>
<p>Saiba mais em nossa <a href="https://exemplo.com/guia">página de referência</a>.</p>
""".strip()

CONTEUDO_RASCUNHO = """
<p>Rascunho inicial sobre boas práticas de acessibilidade em conteúdo web.
Ainda em construção: vamos detalhar textos alternativos, hierarquia de títulos e
rótulos de link descritivos.</p>
<h2>Por que acessibilidade importa?</h2>
<p>Conteúdo acessível alcança mais pessoas e melhora o SEO ao mesmo tempo.</p>
""".strip()

CONTEUDO_AGENDADO = """
<p>Neste artigo agendado vamos comparar estratégias de conteúdo para captação de
leads em pequenas empresas, com um passo a passo aplicável já na próxima semana.</p>
<h2>Quais canais priorizar?</h2>
<p>Comece pelos canais onde seu público já está e meça os resultados com dados.</p>
<ul>
  <li>Conteúdo de blog otimizado para busca.</li>
  <li>E-mail marketing segmentado.</li>
</ul>
""".strip()


class Command(BaseCommand):
    help = "Popula categorias, tags e posts de demonstração do blog (idempotente)."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        from apps.blog.models import Category, Post, Tag
        from apps.blog.validation import validate_post

        autor = self._obter_usuario()
        categorias = self._criar_categorias(Category)
        tags = self._criar_tags(Tag)

        agora = timezone.now()
        definicoes = [
            {
                "title": "Guia prático de SEO e GEO para blogs em 2026",
                "excerpt": "Um resumo direto do que move o ponteiro em SEO e GEO, com exemplos aplicáveis hoje.",
                "content": CONTEUDO_PUBLICADO,
                "status": Post.Status.PUBLISHED,
                "focus_keyword": "seo",
                "meta_title": "Guia prático de SEO e GEO para blogs em 2026",
                "meta_description": "Aprenda a estruturar artigos para SEO e GEO com títulos, listas, dados e fontes — um guia direto e aplicável para o seu blog.",
                "featured_image_alt": "Ilustração de um painel de métricas de SEO",
                "published_at": agora - timedelta(days=2),
                "publish_at": None,
                "categorias": ["Tecnologia"],
                "tags": ["seo", "geo", "web"],
            },
            {
                "title": "Acessibilidade em conteúdo web: por onde começar",
                "excerpt": "",
                "content": CONTEUDO_RASCUNHO,
                "status": Post.Status.DRAFT,
                "focus_keyword": "acessibilidade",
                "meta_title": "",
                "meta_description": "",
                "featured_image_alt": "",
                "published_at": None,
                "publish_at": None,
                "categorias": ["Tecnologia"],
                "tags": ["web"],
            },
            {
                "title": "Estratégias de conteúdo para captar leads",
                "excerpt": "Passo a passo para priorizar canais e medir resultados na captação de leads.",
                "content": CONTEUDO_AGENDADO,
                "status": Post.Status.SCHEDULED,
                "focus_keyword": "leads",
                "meta_title": "Estratégias de conteúdo para captar leads",
                "meta_description": "Descubra quais canais priorizar para captar leads em pequenas empresas e como medir os resultados com dados confiáveis.",
                "featured_image_alt": "",
                "published_at": None,
                "publish_at": agora + timedelta(days=3),
                "categorias": ["Marketing"],
                "tags": ["seo"],
            },
        ]

        criados = 0
        for dados in definicoes:
            post, criado = Post.objects.get_or_create(
                slug=slugify(dados["title"])[:210],
                defaults={
                    "author": autor,
                    "title": dados["title"],
                    "excerpt": dados["excerpt"],
                    "content": dados["content"],
                    "status": dados["status"],
                    "focus_keyword": dados["focus_keyword"],
                    "meta_title": dados["meta_title"],
                    "meta_description": dados["meta_description"],
                    "featured_image_alt": dados["featured_image_alt"],
                    "published_at": dados["published_at"],
                    "publish_at": dados["publish_at"],
                },
            )
            if not criado:
                continue

            post.categories.set([categorias[nome] for nome in dados["categorias"] if nome in categorias])
            post.tags.set([tags[nome] for nome in dados["tags"] if nome in tags])

            # Roda a validação síncrona para preencher as pontuações.
            report = validate_post(post)
            post.seo_score = report["seo"]["score"]
            post.geo_score = report["geo"]["score"]
            post.a11y_score = report["accessibility"]["score"]
            post.last_validation = report
            post.validated_at = timezone.now()
            post.save(update_fields=[
                "seo_score", "geo_score", "a11y_score", "last_validation", "validated_at",
            ])
            criados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed do blog concluído: {len(categorias)} categoria(s), "
                f"{len(tags)} tag(s) e {criados} post(s) novo(s)."
            )
        )

    # -- Passos -------------------------------------------------------------
    def _obter_usuario(self):
        """Retorna um usuário admin existente (ou ``None``; o FK é opcional)."""
        Usuario = get_user_model()
        usuario = (
            Usuario.objects.filter(is_superuser=True).order_by("pk").first()
            or Usuario.objects.filter(is_staff=True).order_by("pk").first()
        )
        if usuario is None:
            self.stdout.write(
                self.style.WARNING(
                    "Nenhum usuário admin encontrado; os posts ficam sem autor."
                )
            )
        return usuario

    def _criar_categorias(self, Category) -> dict:
        categorias = {}
        for nome, descricao in CATEGORIAS_DEMO:
            categoria, _criada = Category.objects.get_or_create(
                slug=slugify(nome)[:110],
                defaults={"name": nome, "description": descricao},
            )
            categorias[nome] = categoria
        return categorias

    def _criar_tags(self, Tag) -> dict:
        tags = {}
        for nome in TAGS_DEMO:
            tag, _criada = Tag.objects.get_or_create(
                slug=slugify(nome)[:70],
                defaults={"name": nome},
            )
            tags[nome] = tag
        return tags

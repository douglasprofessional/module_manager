"""Views do módulo Blog (gestão interna — somente staff).

Funde a gestão de conteúdo (antes em ``dashboard/views.py`` do ``djangopress``)
com o que era necessário do editor do blog. Tudo exige administrador
(``is_staff``) via ``@admin_requerido``; o ``SomenteAdminMiddleware`` já protege
o site inteiro (defesa em profundidade). As ações que gravam são POST/CSRF.

Destaque: o editor de posts roda o motor de validação (SEO/GEO/Acessibilidade)
a CADA clique em Salvar / Rascunho / Enviar para revisão / Publicar / Agendar,
tanto no servidor (autoritativo, aqui) quanto ao vivo via AJAX (``validate_ajax``).

Como a plataforma é 100% administrativa, todo staff pode tudo: as checagens de
papel do template original foram substituídas pelos helpers de
``apps.blog.permissions`` (que retornam ``True`` para qualquer staff).
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from apps.blog import permissions
from apps.blog.forms import CategoryForm, PostForm, TagForm
from apps.blog.models import Category, Post, Tag
from apps.blog.seo_utils import enhance_content_html, make_excerpt, truncate
from apps.blog.validation import run_validation
from apps.contas.decorators import admin_requerido

logger = logging.getLogger("modulos.blog.views")

# Ações possíveis nos botões do editor.
ACTIONS = {"save", "draft", "pending", "publish", "schedule", "unpublish"}

# Dimensões exibidas no painel de validação.
DIMS = [("seo", "SEO"), ("geo", "GEO"), ("accessibility", "Acessibilidade")]


# --------------------------------------------------------------------------- #
# Auditoria (best-effort — nunca quebra a view)
# --------------------------------------------------------------------------- #
def _ip(request: HttpRequest) -> str | None:
    return request.META.get("REMOTE_ADDR") or None


def _auditar(request: HttpRequest, acao: str, objeto: str = "") -> None:
    """Registra um evento de auditoria sem nunca quebrar o fluxo da view."""
    try:
        from apps.nucleo.models import RegistroAuditoria

        usuario = request.user if getattr(request.user, "is_authenticated", False) else None
        RegistroAuditoria.objects.create(
            usuario=usuario,
            acao=acao,
            objeto_repr=(objeto or "")[:255],
            ip=_ip(request),
        )
    except Exception:  # auditoria é best-effort
        logger.exception("Falha ao registrar auditoria (acao=%s).", acao)


# --------------------------------------------------------------------------- #
# Listagem de posts (tela inicial do módulo)
# --------------------------------------------------------------------------- #
@admin_requerido
def lista(request: HttpRequest) -> HttpResponse:
    """Lista de posts com filtros por status e busca por título/conteúdo."""
    posts = Post.objects.select_related("author")

    status = request.GET.get("status")
    if status in dict(Post.Status.choices):
        posts = posts.filter(status=status)
    q = (request.GET.get("q") or "").strip()
    if q:
        posts = posts.filter(Q(title__icontains=q) | Q(content__icontains=q))

    contagem = Post.objects.aggregate(
        publicados=Count("id", filter=Q(status=Post.Status.PUBLISHED)),
        rascunhos=Count("id", filter=Q(status=Post.Status.DRAFT)),
        agendados=Count("id", filter=Q(status=Post.Status.SCHEDULED)),
    )

    contexto = {
        "posts": posts,
        "status_choices": Post.Status.choices,
        "current_status": status or "",
        "q": q,
        "contagem": contagem,
    }
    return render(request, "blog/lista.html", contexto)


# --------------------------------------------------------------------------- #
# Editor de posts (criar/editar)
# --------------------------------------------------------------------------- #
@admin_requerido
@ensure_csrf_cookie  # garante o cookie CSRF para o fetch() do validador ao vivo
@require_http_methods(["GET", "POST"])
def post_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Cria (``pk`` ausente) ou edita um post, rodando a validação a cada envio."""
    post = None
    if pk is not None:
        post = get_object_or_404(Post, pk=pk)

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        action = request.POST.get("action", "save")
        if action not in ACTIONS:
            action = "save"

        if form.is_valid():
            return _processar_envio_editor(request, form, post, action)
        messages.error(request, "Corrija os erros do formulário destacados abaixo.")
        report = post.last_validation if post else {}
    else:
        form = PostForm(instance=post)
        report = post.last_validation if post else {}

    contexto = {
        "form": form,
        "post": post,
        "report": report,
        "dims": DIMS,
        "can_publish": permissions.pode_publicar(request.user),
        "is_new": post is None,
    }
    return render(request, "blog/post_form.html", contexto)


def _editor_payload(obj):
    """Monta o dict de validação a partir do objeto Post ainda não salvo."""
    return {
        "title": obj.title,
        "meta_title": obj.meta_title,
        "meta_description": obj.meta_description,
        "slug": obj.slug or slugify(obj.title),
        "focus_keyword": obj.focus_keyword,
        "excerpt": obj.excerpt,
        "content": obj.content,
        "has_featured_image": bool(obj.featured_image),
        "featured_image_alt": obj.featured_image_alt,
        "author_name": permissions.nome_exibicao(obj.author) if obj.author_id else "",
        "site": None,
    }


def _aplicar_melhores_praticas(obj):
    """
    'Aplicação de melhores práticas': preenche automaticamente campos vazios e
    higieniza o HTML (lazy-load em imagens, rel seguro em links, âncoras nos títulos).
    """
    if obj.content:
        obj.content = enhance_content_html(obj.content)
    if not obj.excerpt and obj.content:
        obj.excerpt = make_excerpt(obj.content)
    if not obj.meta_title and obj.title:
        obj.meta_title = truncate(obj.title, 70)
    if not obj.meta_description:
        obj.meta_description = truncate(obj.excerpt or make_excerpt(obj.content), 160)


def _processar_envio_editor(request, form, post, action):
    obj = form.save(commit=False)
    if obj.author_id is None:
        obj.author = request.user

    # 1) Aplica melhores práticas automáticas.
    _aplicar_melhores_praticas(obj)

    # 2) Roda a validação no servidor (SEMPRE — a cada clique de botão).
    report = run_validation(_editor_payload(obj))
    obj.seo_score = report["seo"]["score"]
    obj.geo_score = report["geo"]["score"]
    obj.a11y_score = report["accessibility"]["score"]
    obj.last_validation = report
    obj.validated_at = timezone.now()

    blocked = not report["can_publish"]

    # 3) Rede de segurança: quem não pode publicar/agendar envia para revisão.
    #    Na plataforma todo staff pode publicar, então este ramo é inócuo — mas
    #    é mantido para preservar a semântica original.
    if action in {"publish", "schedule"} and not permissions.pode_publicar(request.user):
        action = "pending"
        messages.warning(request, "Seu papel não permite publicar. O post foi enviado para revisão.")

    # 4) Resolve o status conforme a ação (e os bloqueios de validação).
    published_now = False
    scheduled_now = False
    error_added = False
    if action == "publish":
        if blocked:
            messages.error(
                request,
                "Não foi possível publicar: corrija os itens obrigatórios "
                f"({', '.join(report['blocking_issues'])}).",
            )
            error_added = True
        else:
            obj.status = Post.Status.PUBLISHED
            obj.published_at = obj.published_at or timezone.now()
            obj.publish_at = None
            published_now = True
    elif action == "schedule":
        if not obj.publish_at:
            messages.error(request, "Informe a data/hora de agendamento.")
            error_added = True
        elif obj.publish_at <= timezone.now():
            messages.error(request, "A data de agendamento precisa ser no futuro.")
            error_added = True
        elif blocked:
            messages.error(
                request,
                "Não foi possível agendar: corrija os itens obrigatórios "
                f"({', '.join(report['blocking_issues'])}).",
            )
            error_added = True
        else:
            obj.status = Post.Status.SCHEDULED
            obj.published_at = None
            scheduled_now = True
    elif action == "pending":
        obj.status = Post.Status.PENDING
    elif action == "draft":
        obj.status = Post.Status.DRAFT
    elif action == "unpublish":
        obj.status = Post.Status.DRAFT
        obj.published_at = None
    # 'save' mantém o status atual (rascunho para posts novos).

    obj.save()
    form.save_m2m()
    form.save_tags(obj)

    if published_now:
        messages.success(request, "Post publicado com sucesso!")
        _auditar(request, "blog:post_publicado", objeto=str(obj))
    elif scheduled_now:
        messages.success(request, f"Post agendado para {obj.publish_at:%d/%m/%Y %H:%M}.")
        _auditar(request, "blog:post_agendado", objeto=str(obj))
    elif not error_added:
        messages.success(request, "Alterações salvas. Validação atualizada.")
        _auditar(request, "blog:post_salvo", objeto=str(obj))

    return redirect("blog:post_edit", pk=obj.pk)


@admin_requerido
@require_http_methods(["GET", "POST"])
def post_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Confirma (GET) e efetua (POST) a exclusão de um post."""
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        rotulo = str(post)
        post.delete()
        _auditar(request, "blog:post_excluido", objeto=rotulo)
        messages.success(request, "Post excluído.")
        return redirect("blog:lista")
    contexto = {
        "objeto": post,
        "tipo": "post",
        "url_cancelar": "blog:lista",
    }
    return render(request, "blog/confirmar_exclusao.html", contexto)


# --------------------------------------------------------------------------- #
# Endpoint AJAX: validação ao vivo (chamado a cada clique/digitação no editor)
# --------------------------------------------------------------------------- #
@admin_requerido
@require_POST
def validate_ajax(request: HttpRequest) -> JsonResponse:
    """Roda a validação ao vivo a partir dos campos enviados pelo editor."""
    payload = {
        "title": request.POST.get("title", ""),
        "meta_title": request.POST.get("meta_title", ""),
        "meta_description": request.POST.get("meta_description", ""),
        "slug": request.POST.get("slug", ""),
        "focus_keyword": request.POST.get("focus_keyword", ""),
        "excerpt": request.POST.get("excerpt", ""),
        "content": request.POST.get("content", ""),
        "has_featured_image": request.POST.get("has_featured_image") == "1",
        "featured_image_alt": request.POST.get("featured_image_alt", ""),
        "author_name": permissions.nome_exibicao(request.user),
        "site": None,
    }
    return JsonResponse(run_validation(payload))


# --------------------------------------------------------------------------- #
# Categorias
# --------------------------------------------------------------------------- #
@admin_requerido
def category_list(request: HttpRequest) -> HttpResponse:
    categorias = Category.objects.annotate(num_posts=Count("posts")).order_by("name")
    return render(request, "blog/categorias.html", {"categorias": categorias})


@admin_requerido
@require_http_methods(["GET", "POST"])
def category_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    obj = get_object_or_404(Category, pk=pk) if pk is not None else None
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=obj)
        if form.is_valid():
            categoria = form.save()
            _auditar(request, "blog:categoria_salva", objeto=categoria.name)
            messages.success(request, "Categoria salva.")
            return redirect("blog:category_list")
    else:
        form = CategoryForm(instance=obj)
    contexto = {
        "form": form,
        "is_new": obj is None,
        "tipo": "categoria",
        "url_lista": "blog:category_list",
    }
    return render(request, "blog/taxonomia_form.html", contexto)


@admin_requerido
@require_http_methods(["GET", "POST"])
def category_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        rotulo = obj.name
        obj.delete()
        _auditar(request, "blog:categoria_excluida", objeto=rotulo)
        messages.success(request, "Categoria excluída.")
        return redirect("blog:category_list")
    contexto = {
        "objeto": obj,
        "tipo": "categoria",
        "url_cancelar": "blog:category_list",
    }
    return render(request, "blog/confirmar_exclusao.html", contexto)


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
@admin_requerido
def tag_list(request: HttpRequest) -> HttpResponse:
    tags = Tag.objects.annotate(num_posts=Count("posts")).order_by("name")
    return render(request, "blog/tags.html", {"tags": tags})


@admin_requerido
@require_http_methods(["GET", "POST"])
def tag_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    obj = get_object_or_404(Tag, pk=pk) if pk is not None else None
    if request.method == "POST":
        form = TagForm(request.POST, instance=obj)
        if form.is_valid():
            tag = form.save()
            _auditar(request, "blog:tag_salva", objeto=tag.name)
            messages.success(request, "Tag salva.")
            return redirect("blog:tag_list")
    else:
        form = TagForm(instance=obj)
    contexto = {
        "form": form,
        "is_new": obj is None,
        "tipo": "tag",
        "url_lista": "blog:tag_list",
    }
    return render(request, "blog/taxonomia_form.html", contexto)


@admin_requerido
@require_http_methods(["GET", "POST"])
def tag_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Tag, pk=pk)
    if request.method == "POST":
        rotulo = obj.name
        obj.delete()
        _auditar(request, "blog:tag_excluida", objeto=rotulo)
        messages.success(request, "Tag excluída.")
        return redirect("blog:tag_list")
    contexto = {
        "objeto": obj,
        "tipo": "tag",
        "url_cancelar": "blog:tag_list",
    }
    return render(request, "blog/confirmar_exclusao.html", contexto)

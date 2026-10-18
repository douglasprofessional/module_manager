"""Filtros e tags de template do módulo Blog.

Carregue com ``{% load blog_extras %}``.

Filtros:
    get_item     — acessa ``dict[key]`` no template (para chaves dinâmicas).
    status_icon  — ícone textual conforme o status de uma checagem de validação.
    score_class  — classe CSS conforme a pontuação (0–100): good / ok / bad.
    initials     — até 2 letras maiúsculas a partir de um nome (avatar).

Tags:
    querystring  — preserva a query string atual trocando/adicionando parâmetros.
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Acessa dict[key] no template: {{ meudict|get_item:chave }}."""
    if hasattr(dictionary, "get"):
        return dictionary.get(key)
    return None


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """
    Preserva a query string atual trocando/adicionando parâmetros.
    Uso: <a href="?{% querystring page=3 %}">...</a>
    """
    request = context.get("request")
    params = request.GET.copy() if request else {}
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def status_icon(status):
    """Ícone textual conforme o status de uma checagem de validação."""
    return {"pass": "✓", "warn": "!", "fail": "✕"}.get(status, "•")


@register.filter
def score_class(value):
    """Classe CSS conforme a pontuação (0–100): good / ok / bad."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "bad"
    if v >= 80:
        return "good"
    if v >= 50:
        return "ok"
    return "bad"


@register.filter
def initials(name):
    parts = (name or "").split()
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

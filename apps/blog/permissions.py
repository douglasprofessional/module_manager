"""Helpers de permissão do módulo Blog.

A plataforma de destino é 100% administrativa: todo acesso ao sistema exige
``is_staff`` (garantido pelo middleware e pelos decorators/mixins de ``contas``).
Portanto, aqui a regra é simples: **todo usuário staff pode tudo** no blog
(editar qualquer post, publicar, agendar, excluir). Estas funções existem para
manter as views legíveis e para concentrar num só lugar qualquer futura
diferenciação de papéis.

Todas recebem o ``user`` (e, quando fizer sentido, o ``post``) e devolvem bool.
São resilientes a ``user`` anônimo/``None``.
"""
from __future__ import annotations


def _e_staff(user) -> bool:
    """Verdadeiro quando ``user`` está autenticado e é staff."""
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
    )


def pode_editar_post(user, post=None) -> bool:
    """Todo staff pode editar qualquer post."""
    return _e_staff(user)


def pode_publicar(user) -> bool:
    """Todo staff pode publicar/agendar."""
    return _e_staff(user)


def pode_editar_de_outros(user) -> bool:
    """Todo staff enxerga e edita os posts de todos os autores."""
    return _e_staff(user)


def pode_excluir_post(user, post=None) -> bool:
    """Todo staff pode excluir qualquer post."""
    return _e_staff(user)


def nome_exibicao(user) -> str:
    """Nome de exibição do usuário (substitui o antigo ``user.display_name``)."""
    if user is None:
        return ""
    try:
        return user.get_full_name()
    except Exception:
        return getattr(user, "email", "") or ""

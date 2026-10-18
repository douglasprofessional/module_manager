"""Manager do modelo de usuário: criação de usuários e superusuários por e-mail."""
from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class UsuarioManager(BaseUserManager):
    """Manager que cria usuários identificados por e-mail (sem username)."""

    use_in_migrations = True

    def _criar_usuario(self, email: str, password: str | None, **campos_extra: Any):
        """Cria e salva um usuário aplicando hash na senha via ``set_password``."""
        if not email:
            raise ValueError(_("O e-mail é obrigatório."))
        email = self.normalize_email(email)
        usuario = self.model(email=email, **campos_extra)
        # set_password gera o hash (nunca armazenar senha em texto puro).
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email: str, password: str | None = None, **campos_extra: Any):
        """Cria um usuário comum (sem acesso ao sistema por padrão)."""
        campos_extra.setdefault("is_staff", False)
        campos_extra.setdefault("is_superuser", False)
        campos_extra.setdefault("is_active", True)
        return self._criar_usuario(email, password, **campos_extra)

    def create_superuser(self, email: str, password: str | None = None, **campos_extra: Any):
        """Cria um superusuário, forçando ``is_staff`` e ``is_superuser`` como True."""
        campos_extra.setdefault("is_staff", True)
        campos_extra.setdefault("is_superuser", True)
        campos_extra.setdefault("is_active", True)

        if campos_extra.get("is_staff") is not True:
            raise ValueError(_("Superusuário precisa de is_staff=True."))
        if campos_extra.get("is_superuser") is not True:
            raise ValueError(_("Superusuário precisa de is_superuser=True."))

        return self._criar_usuario(email, password, **campos_extra)

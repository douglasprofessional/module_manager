"""Modelo de usuário do sistema (autenticação por e-mail, somente administradores)."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contas.managers import UsuarioManager
from apps.nucleo.validators import validar_imagem_perfil


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Usuário administrador.

    Autenticação por e-mail. O acesso ao sistema exige ``is_staff=True``
    (garantido pelo middleware e pelos mixins/decorators do app ``contas``).
    A senha é sempre armazenada em hash (herança de ``AbstractBaseUser``).
    """

    email = models.EmailField(_("e-mail"), unique=True)
    nome_completo = models.CharField(_("nome completo"), max_length=255, blank=True)
    is_active = models.BooleanField(
        _("ativo"),
        default=True,
        help_text=_("Desmarque para desativar a conta em vez de excluí-la."),
    )
    is_staff = models.BooleanField(
        _("acesso ao sistema"),
        default=False,
        help_text=_("Indica que o usuário pode acessar o sistema (obrigatório)."),
    )
    date_joined = models.DateTimeField(_("data de cadastro"), default=timezone.now)
    ultimo_ip = models.GenericIPAddressField(_("último IP"), null=True, blank=True)
    foto = models.FileField(
        _("foto"),
        upload_to="perfis/",
        blank=True,
        null=True,
        validators=[validar_imagem_perfil],
        help_text=_("PNG, JPG, WEBP ou GIF. Até 2 MB."),
    )

    class Tema(models.TextChoices):
        CLARO = "claro", _("Claro")
        ESCURO = "escuro", _("Escuro")

    tema = models.CharField(
        _("tema"),
        max_length=10,
        choices=Tema.choices,
        default=Tema.CLARO,
        help_text=_("Preferência de tema visual deste usuário."),
    )

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = ["nome_completo"]

    class Meta:
        verbose_name = _("usuário")
        verbose_name_plural = _("usuários")
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        """Nome completo, com fallback para o e-mail."""
        return (self.nome_completo or "").strip() or self.email

    def get_short_name(self) -> str:
        """Primeiro nome, com fallback para o e-mail."""
        nome = (self.nome_completo or "").strip()
        return nome.split(" ")[0] if nome else self.email

    @property
    def foto_url(self) -> str:
        """URL da foto de perfil, ou ``""`` quando não houver (usa iniciais)."""
        try:
            return self.foto.url if self.foto else ""
        except Exception:
            return ""

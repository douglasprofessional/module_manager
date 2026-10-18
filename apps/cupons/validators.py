"""Validadores reutilizaveis do modulo de cupons.

Copia local das mesmas regex do antigo ``apps.core.validators`` (o modulo de
cupons e autocontido: NAO importa ``apps.core``).
"""

from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r"^[0-9\s()+\-.]{8,30}$",
    message="Informe um telefone valido (ex.: (11) 98888-7777).",
    code="telefone_invalido",
)

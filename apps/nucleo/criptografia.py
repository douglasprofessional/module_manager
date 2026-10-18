"""Criptografia simétrica de segredos (seção 9 da SPEC).

Expõe ``criptografar(txt) -> str`` e ``descriptografar(txt) -> str`` usando
``cryptography.fernet.Fernet`` com a chave ``modulos_FERNET_KEY``.

Em produção (``DEBUG=False``) a chave é obrigatória. Em desenvolvimento
(``DEBUG=True``), se a chave não existir, deriva-se uma chave EFÊMERA a partir
do ``SECRET_KEY`` (SHA-256 -> base64 urlsafe) e avisa-se via ``logging``. Uma
chave efêmera muda quando o ``SECRET_KEY`` muda, invalidando dados cifrados —
por isso serve apenas para desenvolvimento.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("modulos.nucleo.criptografia")

# Instância de Fernet resolvida sob demanda e reaproveitada (o aviso de chave
# efêmera é emitido uma única vez).
_fernet: Fernet | None = None


def _derivar_chave_efemera(secret_key: str) -> bytes:
    """Deriva uma chave Fernet válida (32 bytes -> base64 urlsafe) do SECRET_KEY."""
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _obter_fernet() -> Fernet:
    """Retorna a instância de ``Fernet`` a ser usada, resolvendo a chave uma vez."""
    global _fernet
    if _fernet is not None:
        return _fernet

    chave = getattr(settings, "modulos_FERNET_KEY", "") or ""
    if chave:
        chave_bytes = chave.encode("utf-8") if isinstance(chave, str) else chave
    elif getattr(settings, "DEBUG", False):
        chave_bytes = _derivar_chave_efemera(settings.SECRET_KEY)
        logger.warning(
            "modulos_FERNET_KEY ausente: usando chave EFÊMERA derivada do "
            "SECRET_KEY (apenas DEBUG). Segredos cifrados agora ficam inválidos "
            "se o SECRET_KEY mudar. Defina modulos_FERNET_KEY para persistência."
        )
    else:
        raise ImproperlyConfigured(
            "modulos_FERNET_KEY é obrigatória em produção (DEBUG=False) para "
            "criptografar segredos."
        )

    try:
        _fernet = Fernet(chave_bytes)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "modulos_FERNET_KEY inválida: precisa ser uma chave Fernet "
            "(32 bytes codificados em base64 urlsafe)."
        ) from exc
    return _fernet


def criptografar(txt: str) -> str:
    """Cifra ``txt`` e retorna o token (texto ASCII) pronto para persistir."""
    if txt is None:
        raise ValueError("Nada a criptografar: 'txt' é None.")
    token = _obter_fernet().encrypt(txt.encode("utf-8"))
    return token.decode("ascii")


def descriptografar(txt: str) -> str:
    """Decifra um token gerado por ``criptografar`` e retorna o texto original."""
    if not txt:
        return ""
    valor = _obter_fernet().decrypt(txt.encode("utf-8"))
    return valor.decode("utf-8")

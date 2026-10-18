#!/usr/bin/env python
"""Utilitário de linha de comando do Django para tarefas administrativas do Gerenciador de Módulos."""
from __future__ import annotations

import os
import sys


def main() -> None:
    """Executa tarefas administrativas apontando para as settings do projeto."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - erro de ambiente
        raise ImportError(
            "Não foi possível importar o Django. Verifique se ele está instalado "
            "e disponível na variável de ambiente PYTHONPATH e se o ambiente "
            "virtual está ativado."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

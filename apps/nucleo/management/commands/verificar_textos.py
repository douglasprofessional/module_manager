"""Comando ``verificar_textos``: confere as chaves de ``apps/nucleo/textos.py``.

Varre os templates (tag ``texto`` com a chave entre aspas) e o código Python
(chamadas da função ``texto`` com a chave literal) e lista as chaves usadas que NÃO existem no arquivo
central de textos. Útil depois de renomear/remover uma chave.

Uso::

    python manage.py verificar_textos
    python manage.py verificar_textos --nao-usadas   # também lista as sobrando

Sai com código 1 quando há chaves ausentes (pode ser usado em CI).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.nucleo.textos import existe, todas_as_chaves

# Tag de template "texto" e chamadas Python da função "texto" com chave literal.
_RE_TEMPLATE = re.compile(r"""\{%\s*texto\s+["']([^"']+)["']""")
_RE_PYTHON = re.compile(r"""\btexto\(\s*["']([^"']+)["']""")


class Command(BaseCommand):
    """Lista chaves de texto usadas no projeto e ausentes em ``textos.py``."""

    help = "Confere se todas as chaves de texto usadas existem em apps/nucleo/textos.py."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--nao-usadas",
            action="store_true",
            help="Também lista as chaves definidas e não encontradas em nenhum arquivo.",
        )

    def handle(self, *args: Any, **opcoes: Any) -> None:
        base = Path(settings.BASE_DIR)
        usadas: dict[str, list[str]] = {}

        for pasta, padrao, regex in (
            (base / "templates", "*.html", _RE_TEMPLATE),
            (base / "apps", "*.html", _RE_TEMPLATE),
            (base / "apps", "*.py", _RE_PYTHON),
        ):
            if not pasta.exists():
                continue
            for arquivo in pasta.rglob(padrao):
                if "migrations" in arquivo.parts:
                    continue
                conteudo = arquivo.read_text(encoding="utf-8", errors="ignore")
                for chave in regex.findall(conteudo):
                    usadas.setdefault(chave, []).append(str(arquivo.relative_to(base)))

        ausentes = {chave: locais for chave, locais in usadas.items() if not existe(chave)}
        for chave, locais in sorted(ausentes.items()):
            self.stdout.write(self.style.ERROR(f"AUSENTE  {chave}  ->  {', '.join(sorted(set(locais)))}"))

        if opcoes.get("nao_usadas"):
            for chave in sorted(todas_as_chaves() - set(usadas)):
                self.stdout.write(f"não usada  {chave}")

        if ausentes:
            raise CommandError(f"{len(ausentes)} chave(s) de texto ausente(s) em apps/nucleo/textos.py.")
        self.stdout.write(self.style.SUCCESS(f"OK: {len(usadas)} chave(s) usadas, todas definidas."))

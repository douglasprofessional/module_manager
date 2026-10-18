"""Semeia a biblioteca de 10 modelos (templates) de e-mail, de forma idempotente.

Os modelos vêm de ``apps.email_marketing.templates_prontos.TEMPLATES_PRONTOS``.
São criados por ``get_or_create`` pela chave natural ``nome`` — modelos já
existentes NÃO são sobrescritos (preserva edições feitas pelo administrador).
Roda a cada boot (via entrypoint), pois a biblioteca é um recurso do produto e
não um dado de demonstração.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("modulos.email_marketing.seed_templates")


class Command(BaseCommand):
    help = "Cria/garante os 10 modelos de e-mail prontos (idempotente)."

    def handle(self, *args, **opcoes) -> None:
        from apps.email_marketing.models import TemplateEmail

        try:
            from apps.email_marketing.templates_prontos import TEMPLATES_PRONTOS
        except Exception:
            logger.exception("Não foi possível importar TEMPLATES_PRONTOS.")
            self.stderr.write("templates_prontos.py ausente ou inválido; nada a semear.")
            return

        criados = 0
        for item in TEMPLATES_PRONTOS:
            nome = (item.get("nome") or "").strip()
            if not nome:
                continue
            _obj, foi_criado = TemplateEmail.objects.get_or_create(
                nome=nome,
                defaults={
                    "descricao": item.get("descricao", "")[:240],
                    "categoria": item.get("categoria", TemplateEmail.Categoria.SIMPLES),
                    "corpo_html": item.get("corpo_html", ""),
                    "corpo_texto": item.get("corpo_texto", ""),
                    "builtin": True,
                    "ativo": True,
                },
            )
            if foi_criado:
                criados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Biblioteca de modelos de e-mail: {criados} novo(s); "
                f"{TemplateEmail.objects.count()} no total."
            )
        )

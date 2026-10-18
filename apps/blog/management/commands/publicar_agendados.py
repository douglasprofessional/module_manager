"""Comando ``publicar_agendados``: publica posts agendados cujo prazo venceu.

Substitui a tarefa Celery ``publish_scheduled_posts`` do template original. Deve
ser executado periodicamente (ex.: cron / agendador do sistema, a cada minuto):

    python manage.py publicar_agendados

Publica todo post em ``SCHEDULED`` com ``publish_at <= agora``. Idempotente:
posts sem prazo vencido não são tocados.
"""
from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Publica posts agendados (SCHEDULED) cujo publish_at já venceu."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        from apps.blog.models import Post

        agora = timezone.now()
        vencidos = Post.objects.filter(
            status=Post.Status.SCHEDULED, publish_at__lte=agora
        )

        publicados = 0
        for post in vencidos:
            post.publish(when=post.publish_at or agora)
            publicados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{publicados} post(s) agendado(s) publicado(s) em {agora.isoformat()}."
            )
        )

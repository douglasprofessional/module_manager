"""Comando ``seed_kanban``: popula um quadro de demonstração.

Cria o quadro "Comercial" com as colunas [Backlog, Em andamento, Revisão,
Concluído] e ~8 cartões distribuídos, com prioridades variadas, alguns com prazo
(inclusive 1 atrasado) e responsável = primeiro superusuário existente (ou
``None``). NÃO faz nenhuma chamada externa.

Idempotente: reexecutar NÃO duplica. O quadro é chaveado pelo nome
(``get_or_create``), as colunas por (quadro, nome) e os cartões por
(coluna, título). Os prazos são relativos a hoje para que a situação de atraso
seja sempre coerente.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.kanban.models import Cartao, Coluna, Quadro

logger = logging.getLogger("modulos.kanban.seed")

NOME_QUADRO_DEMO = "Comercial"

# Colunas do quadro, na ordem em que aparecem no board.
COLUNAS_DEMO = ["Backlog", "Em andamento", "Revisão", "Concluído"]

# Cartões de demonstração. 'prazo_em_dias' é relativo a hoje (None = sem prazo).
# Um cartão fica atrasado (prazo negativo e não concluído).
CARTOES_DEMO: list[dict[str, Any]] = [
    {
        "coluna": "Backlog",
        "titulo": "Mapear leads do setor de varejo",
        "descricao": "Levantar comércios sem site na região central.",
        "prioridade": Cartao.Prioridade.MEDIA,
        "prazo_em_dias": None,
        "concluido": False,
    },
    {
        "coluna": "Backlog",
        "titulo": "Preparar proposta comercial padrão",
        "descricao": "Modelo reutilizável para envio rápido.",
        "prioridade": Cartao.Prioridade.BAIXA,
        "prazo_em_dias": 10,
        "concluido": False,
    },
    {
        "coluna": "Em andamento",
        "titulo": "Ligar para Padaria Pão Dourado",
        "descricao": "Retomar contato sobre criação de site.",
        "prioridade": Cartao.Prioridade.ALTA,
        "prazo_em_dias": -3,  # atrasado
        "concluido": False,
    },
    {
        "coluna": "Em andamento",
        "titulo": "Enviar orçamento para Auto Peças Silva",
        "descricao": "Site institucional + otimização de SEO.",
        "prioridade": Cartao.Prioridade.URGENTE,
        "prazo_em_dias": 2,
        "concluido": False,
    },
    {
        "coluna": "Em andamento",
        "titulo": "Agendar reunião com Studio Bella",
        "descricao": "Apresentar plano de presença digital.",
        "prioridade": Cartao.Prioridade.MEDIA,
        "prazo_em_dias": 5,
        "concluido": False,
    },
    {
        "coluna": "Revisão",
        "titulo": "Revisar contrato Marcenaria Souza",
        "descricao": "Conferir escopo e prazos antes do envio.",
        "prioridade": Cartao.Prioridade.ALTA,
        "prazo_em_dias": 1,
        "concluido": False,
    },
    {
        "coluna": "Concluído",
        "titulo": "Fechar negócio com Boutique Elegance",
        "descricao": "Contrato assinado e projeto iniciado.",
        "prioridade": Cartao.Prioridade.MEDIA,
        "prazo_em_dias": -1,  # venceu, mas está concluído (não conta como atraso)
        "concluido": True,
    },
    {
        "coluna": "Concluído",
        "titulo": "Follow-up Clínica OdontoVida",
        "descricao": "Confirmar satisfação após entrega.",
        "prioridade": Cartao.Prioridade.BAIXA,
        "prazo_em_dias": None,
        "concluido": True,
    },
]


class Command(BaseCommand):
    """Popula um quadro Kanban de demonstração (sem rede)."""

    help = "Cria o quadro 'Comercial' com colunas e cartões de exemplo (idempotente)."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        usuario = self._obter_usuario()

        quadro = self._criar_quadro(usuario)
        colunas = self._criar_colunas(quadro)
        criados = self._criar_cartoes(colunas, usuario)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed concluído: quadro '{quadro.nome}', "
                f"{len(colunas)} coluna(s) e {criados} cartão(ões)."
            )
        )

    # -- Passos -------------------------------------------------------------
    def _obter_usuario(self):
        """Retorna um usuário admin existente (ou ``None``; o FK é opcional)."""
        Usuario = get_user_model()
        usuario = (
            Usuario.objects.filter(is_superuser=True).order_by("pk").first()
            or Usuario.objects.filter(is_staff=True).order_by("pk").first()
        )
        if usuario is None:
            self.stdout.write(
                self.style.WARNING(
                    "Nenhum usuário admin encontrado; os registros ficam sem responsável."
                )
            )
        return usuario

    def _criar_quadro(self, usuario) -> Quadro:
        quadro, _criado = Quadro.objects.get_or_create(
            nome=NOME_QUADRO_DEMO,
            defaults={
                "descricao": "Pipeline comercial de prospecção e fechamento.",
                "arquivado": False,
                "criado_por": usuario,
            },
        )
        if usuario is not None and quadro.criado_por_id is None:
            quadro.criado_por = usuario
            quadro.save(update_fields=["criado_por"])
        return quadro

    def _criar_colunas(self, quadro: Quadro) -> dict[str, Coluna]:
        colunas: dict[str, Coluna] = {}
        for indice, nome in enumerate(COLUNAS_DEMO, start=1):
            coluna, _criada = Coluna.objects.get_or_create(
                quadro=quadro,
                nome=nome,
                defaults={"ordem": indice},
            )
            colunas[nome] = coluna
        return colunas

    def _criar_cartoes(self, colunas: dict[str, Coluna], usuario) -> int:
        hoje = timezone.localdate()
        # Ordem por coluna (continua a numeração se já houver cartões).
        proxima_ordem: dict[str, int] = {}
        total = 0
        for dados in CARTOES_DEMO:
            nome_coluna = dados["coluna"]
            coluna = colunas.get(nome_coluna)
            if coluna is None:  # coluna ausente por edição manual: pula com segurança
                continue

            if nome_coluna not in proxima_ordem:
                atual = coluna.cartoes.count()
                proxima_ordem[nome_coluna] = atual + 1

            prazo_em_dias = dados["prazo_em_dias"]
            prazo = hoje + dt.timedelta(days=prazo_em_dias) if prazo_em_dias is not None else None

            _cartao, criado = Cartao.objects.get_or_create(
                coluna=coluna,
                titulo=dados["titulo"],
                defaults={
                    "descricao": dados["descricao"],
                    "prioridade": dados["prioridade"],
                    "prazo": prazo,
                    "concluido": dados["concluido"],
                    "responsavel": usuario,
                    "criado_por": usuario,
                    "ordem": proxima_ordem[nome_coluna],
                },
            )
            if criado:
                proxima_ordem[nome_coluna] += 1
                total += 1
        return total

"""Comando ``seed_sla``: popula o banco para demonstrar o módulo de SLA.

Cria 2 políticas ("Padrão" 4h/24h e "Premium" 1h/8h) e ~8 chamados que cobrem
TODAS as situações de SLA de resolução:

- ``dentro``:   aberto recente, com folga de prazo;
- ``em_risco``: aberto com menos de 25% do prazo restante;
- ``estourado``: aberto com o prazo já vencido (sem resolução);
- ``cumprido``: resolvido dentro do prazo;
- ``estourado`` (resolvido): resolvido, porém após o prazo.

Os instantes (``aberto_em``, ``primeira_resposta_em``, ``resolvido_em``) são
derivados de ``timezone.now()`` com ``timedelta`` para produzir cada situação.
O ``Chamado.save()`` calcula os prazos absolutos a partir da política.

NÃO faz nenhuma chamada externa. Idempotente por título (``update_or_create``):
reexecutar atualiza os mesmos registros e reancora os prazos ao momento atual
(``prazo_resposta``/``prazo_resolucao`` voltam a ``None`` para recálculo).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.sla.models import Chamado, Politica

logger = logging.getLogger("modulos.sla.seed")

# Políticas de SLA (nome -> prazos em horas).
POLITICAS_DEMO: list[dict[str, Any]] = [
    {
        "nome": "Padrão",
        "descricao": "Atendimento comercial padrão: resposta em 4h, resolução em 24h.",
        "prazo_resposta_horas": 4,
        "prazo_resolucao_horas": 24,
    },
    {
        "nome": "Premium",
        "descricao": "Atendimento prioritário: resposta em 1h, resolução em 8h.",
        "prazo_resposta_horas": 1,
        "prazo_resolucao_horas": 8,
    },
]

# Chamados de demonstração. Offsets em HORAS relativos a ``agora``:
#   horas_atras     -> aberto_em = agora - horas_atras
#   resposta_apos   -> primeira_resposta_em = aberto_em + resposta_apos (None = sem resposta)
#   resolvido_apos  -> resolvido_em = aberto_em + resolvido_apos (None = não resolvido)
CHAMADOS_DEMO: list[dict[str, Any]] = [
    {
        "titulo": "Erro ao emitir nota fiscal",
        "politica": "Padrão",
        "prioridade": Chamado.Prioridade.ALTA,
        "status": Chamado.Status.ABERTO,
        "solicitante": "Financeiro",
        "horas_atras": 2,
        "resposta_apos": None,
        "resolvido_apos": None,
    },
    {
        "titulo": "Lentidão no sistema de vendas",
        "politica": "Padrão",
        "prioridade": Chamado.Prioridade.MEDIA,
        "status": Chamado.Status.EM_ANDAMENTO,
        "solicitante": "Loja Centro",
        "horas_atras": 20,
        "resposta_apos": 1,
        "resolvido_apos": None,
    },
    {
        "titulo": "Integração de pagamento instável",
        "politica": "Premium",
        "prioridade": Chamado.Prioridade.URGENTE,
        "status": Chamado.Status.EM_ANDAMENTO,
        "solicitante": "E-commerce",
        "horas_atras": 7,
        "resposta_apos": 0,
        "resolvido_apos": None,
    },
    {
        "titulo": "Servidor de e-mail fora do ar",
        "politica": "Padrão",
        "prioridade": Chamado.Prioridade.URGENTE,
        "status": Chamado.Status.EM_ANDAMENTO,
        "solicitante": "TI Interno",
        "horas_atras": 30,
        "resposta_apos": 2,
        "resolvido_apos": None,
    },
    {
        "titulo": "Falha no backup noturno",
        "politica": "Premium",
        "prioridade": Chamado.Prioridade.ALTA,
        "status": Chamado.Status.PAUSADO,
        "solicitante": "Infraestrutura",
        "horas_atras": 12,
        "resposta_apos": 1,
        "resolvido_apos": None,
    },
    {
        "titulo": "Solicitação de novo usuário",
        "politica": "Padrão",
        "prioridade": Chamado.Prioridade.BAIXA,
        "status": Chamado.Status.RESOLVIDO,
        "solicitante": "RH",
        "horas_atras": 26,
        "resposta_apos": 1,
        "resolvido_apos": 10,
    },
    {
        "titulo": "Reset de senha do gerente",
        "politica": "Premium",
        "prioridade": Chamado.Prioridade.MEDIA,
        "status": Chamado.Status.RESOLVIDO,
        "solicitante": "Diretoria",
        "horas_atras": 20,
        "resposta_apos": 0,
        "resolvido_apos": 5,
    },
    {
        "titulo": "Troca de equipamento com defeito",
        "politica": "Padrão",
        "prioridade": Chamado.Prioridade.MEDIA,
        "status": Chamado.Status.RESOLVIDO,
        "solicitante": "Operações",
        "horas_atras": 50,
        "resposta_apos": 3,
        "resolvido_apos": 40,
    },
]


class Command(BaseCommand):
    """Popula o banco com políticas e chamados de demonstração (sem rede)."""

    help = "Cria 2 políticas de SLA e ~8 chamados cobrindo todas as situações."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        usuario = self._obter_usuario()
        politicas = self._criar_politicas()
        criados = self._criar_chamados(politicas, usuario)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed de SLA concluído: {len(politicas)} política(s) "
                f"e {criados} chamado(s)."
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
                    "Nenhum usuário admin encontrado; os chamados ficam sem responsável."
                )
            )
        return usuario

    def _criar_politicas(self) -> dict[str, Politica]:
        politicas: dict[str, Politica] = {}
        for dados in POLITICAS_DEMO:
            dados = dict(dados)
            nome = dados.pop("nome")
            politica, _criada = Politica.objects.update_or_create(
                nome=nome,
                defaults={**dados, "ativo": True},
            )
            politicas[nome] = politica
        return politicas

    def _criar_chamados(self, politicas: dict[str, Politica], usuario) -> int:
        agora = timezone.now()
        total = 0
        for dados in CHAMADOS_DEMO:
            dados = dict(dados)  # cópia rasa: não mutar a constante
            nome_politica = dados.pop("politica")
            horas_atras = dados.pop("horas_atras")
            resposta_apos = dados.pop("resposta_apos")
            resolvido_apos = dados.pop("resolvido_apos")

            politica = politicas.get(nome_politica)
            if politica is None:
                logger.warning("Política '%s' ausente; chamado ignorado.", nome_politica)
                continue

            aberto_em = agora - timedelta(hours=horas_atras)
            primeira_resposta_em = (
                aberto_em + timedelta(hours=resposta_apos)
                if resposta_apos is not None
                else None
            )
            resolvido_em = (
                aberto_em + timedelta(hours=resolvido_apos)
                if resolvido_apos is not None
                else None
            )

            titulo = dados.pop("titulo")
            campos = {
                **dados,
                "politica": politica,
                "responsavel": usuario,
                "criado_por": usuario,
                "aberto_em": aberto_em,
                "primeira_resposta_em": primeira_resposta_em,
                "resolvido_em": resolvido_em,
                # Zera os prazos para que o save() os reancore ao aberto_em atual.
                "prazo_resposta": None,
                "prazo_resolucao": None,
            }
            # 'titulo' não é único no modelo: usa first() para ser idempotente
            # sem arriscar MultipleObjectsReturned caso exista um chamado de
            # mesmo título criado pela UI. Atualiza o mais antigo do seed ou cria.
            existente = (
                Chamado.objects.filter(titulo=titulo).order_by("id").first()
            )
            if existente is not None:
                for campo, valor in campos.items():
                    setattr(existente, campo, valor)
                existente.save()
            else:
                Chamado.objects.create(titulo=titulo, **campos)
            total += 1
        return total

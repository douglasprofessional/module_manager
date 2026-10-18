"""Comando ``seed_monitoramento``: popula o banco para demonstrar o painel.

Cria ~4 servidores demo (SEM credenciais reais e SEM qualquer acesso SSH) e,
para cada um, ~20 ``LeituraMetrica`` históricas com valores plausíveis (CPU/RAM/
disco variando). Os IPs usados são de faixas de DOCUMENTAÇÃO (TEST-NET,
RFC 5737): ``203.0.113.0/24`` e ``198.51.100.0/24`` — nunca hosts reais.

Cobre os casos pedidos:
- 1 servidor OFFLINE (leituras recentes sem conexão);
- 1 servidor com DISCO CRÍTICO (> 90%).

Idempotente: ``get_or_create`` por nome; as leituras de cada servidor demo são
recriadas a cada execução (contagem estável de ~20). NÃO faz nenhuma chamada de
rede. As datas de coleta são espalhadas via ``update()`` (o campo é
``auto_now_add``) para dar forma ao mini-gráfico.
"""
from __future__ import annotations

import logging
import math
import random
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.monitoramento.models import LeituraMetrica, ServidorVPS

logger = logging.getLogger("modulos.monitoramento.seed")

LEITURAS_POR_SERVIDOR = 20
INTERVALO_MINUTOS = 30  # espaçamento entre leituras (últimas ~10h)

# Servidores fictícios. 'perfil' controla a geração das métricas:
#   ok        -> uso normal, online;
#   disco     -> disco crítico (> 90%), online;
#   offline   -> servidor fora do ar (leituras sem conexão).
SERVIDORES_DEMO: list[dict[str, Any]] = [
    {
        "nome": "web-01",
        "host": "203.0.113.10",
        "porta_ssh": 22,
        "usuario": "root",
        "metodo_auth": ServidorVPS.MetodoAuth.CHAVE,
        "provedor": "Hetzner",
        "tags": "produção, web",
        "observacoes": "Servidor web principal (Nginx + app).",
        "perfil": "ok",
        "nucleos": 4,
        "mem_total_mb": 8192,
        "disco_total_gb": 80.0,
        "base_cpu": 32.0,
        "base_mem": 55.0,
        "base_disco": 48.0,
    },
    {
        "nome": "db-01",
        "host": "203.0.113.20",
        "porta_ssh": 22,
        "usuario": "root",
        "metodo_auth": ServidorVPS.MetodoAuth.CHAVE,
        "provedor": "DigitalOcean",
        "tags": "produção, banco",
        "observacoes": "Banco de dados PostgreSQL — atenção ao disco.",
        "perfil": "disco",
        "nucleos": 8,
        "mem_total_mb": 16384,
        "disco_total_gb": 160.0,
        "base_cpu": 45.0,
        "base_mem": 72.0,
        "base_disco": 93.0,
    },
    {
        "nome": "app-02",
        "host": "198.51.100.30",
        "porta_ssh": 2222,
        "usuario": "deploy",
        "metodo_auth": ServidorVPS.MetodoAuth.SENHA,
        "provedor": "Contabo",
        "tags": "homologação",
        "observacoes": "Ambiente de homologação (fora do ar no momento).",
        "perfil": "offline",
        "nucleos": 2,
        "mem_total_mb": 4096,
        "disco_total_gb": 50.0,
        "base_cpu": 20.0,
        "base_mem": 40.0,
        "base_disco": 35.0,
    },
    {
        "nome": "cache-01",
        "host": "198.51.100.40",
        "porta_ssh": 22,
        "usuario": "root",
        "metodo_auth": ServidorVPS.MetodoAuth.CHAVE,
        "provedor": "AWS Lightsail",
        "tags": "produção, cache",
        "observacoes": "Redis de cache.",
        "perfil": "ok",
        "nucleos": 2,
        "mem_total_mb": 4096,
        "disco_total_gb": 40.0,
        "base_cpu": 18.0,
        "base_mem": 61.0,
        "base_disco": 27.0,
    },
]


class Command(BaseCommand):
    """Popula o banco com servidores e leituras de demonstração (sem rede/SSH)."""

    help = "Cria ~4 servidores demo e ~20 leituras históricas cada (sem SSH)."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        usuario = self._obter_usuario()
        total_servidores = 0
        total_leituras = 0
        for dados in SERVIDORES_DEMO:
            servidor = self._criar_servidor(dados, usuario)
            total_leituras += self._criar_leituras(servidor, dados)
            total_servidores += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed de monitoramento concluído: {total_servidores} servidor(es) "
                f"e {total_leituras} leitura(s)."
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
                    "Nenhum usuário admin encontrado; servidores ficam sem 'criado_por'."
                )
            )
        return usuario

    def _criar_servidor(self, dados: dict[str, Any], usuario) -> ServidorVPS:
        servidor, _criado = ServidorVPS.objects.get_or_create(
            nome=dados["nome"],
            defaults={
                "host": dados["host"],
                "porta_ssh": dados["porta_ssh"],
                "usuario": dados["usuario"],
                "metodo_auth": dados["metodo_auth"],
                "provedor": dados["provedor"],
                "tags": dados["tags"],
                "observacoes": dados["observacoes"],
                "ativo": True,
                "criado_por": usuario,
            },
        )
        # Mantém os dados coerentes ao reexecutar (sem tocar em segredos).
        servidor.host = dados["host"]
        servidor.porta_ssh = dados["porta_ssh"]
        servidor.usuario = dados["usuario"]
        servidor.metodo_auth = dados["metodo_auth"]
        servidor.provedor = dados["provedor"]
        servidor.tags = dados["tags"]
        servidor.observacoes = dados["observacoes"]
        servidor.ativo = True
        if usuario is not None and servidor.criado_por_id is None:
            servidor.criado_por = usuario
        servidor.save()
        return servidor

    def _criar_leituras(self, servidor: ServidorVPS, dados: dict[str, Any]) -> int:
        """Recria ~20 leituras históricas plausíveis para o servidor demo."""
        # Idempotência: zera as leituras deste servidor demo e recria.
        servidor.leituras.all().delete()

        # Gerador determinístico por nome (reexecuções produzem a mesma série).
        rng = random.Random(f"seed-monitoramento::{servidor.nome}")
        agora = timezone.now()
        perfil = dados["perfil"]
        offline = perfil == "offline"

        criadas = 0
        ultima: LeituraMetrica | None = None
        for i in range(LEITURAS_POR_SERVIDOR):
            # i=0 é a mais antiga; a última do laço é a mais recente.
            passos_atras = LEITURAS_POR_SERVIDOR - 1 - i
            quando = agora - timedelta(minutes=INTERVALO_MINUTOS * passos_atras)

            if offline:
                leitura = LeituraMetrica(
                    servidor=servidor,
                    online=False,
                    erro="tempo de conexão/execução esgotado",
                )
            else:
                leitura = self._leitura_online(servidor, dados, rng, i)

            leitura.save()
            # 'coletado_em' é auto_now_add: ajusta via update() para o gráfico.
            LeituraMetrica.objects.filter(pk=leitura.pk).update(coletado_em=quando)
            ultima = leitura
            criadas += 1

        self._ajustar_status(servidor, dados, ultima)
        return criadas

    def _leitura_online(
        self, servidor: ServidorVPS, dados: dict[str, Any], rng: random.Random, i: int
    ) -> LeituraMetrica:
        """Constrói uma leitura online com variação suave em torno das bases."""
        onda = math.sin(i / 2.0)  # variação suave e determinística

        cpu = self._limitar(dados["base_cpu"] + onda * 12 + rng.uniform(-6, 6), 1, 99)
        mem = self._limitar(dados["base_mem"] + onda * 6 + rng.uniform(-4, 4), 5, 97)
        disco = self._limitar(
            dados["base_disco"] + (i * 0.15) + rng.uniform(-0.4, 0.4), 1, 99
        )

        mem_total = dados["mem_total_mb"]
        disco_total = dados["disco_total_gb"]
        uptime = 86400 * 12 + i * INTERVALO_MINUTOS * 60  # ~12 dias + progressão

        return LeituraMetrica(
            servidor=servidor,
            online=True,
            cpu_pct=round(cpu, 1),
            mem_pct=round(mem, 1),
            mem_total_mb=mem_total,
            mem_usada_mb=int(round(mem_total * mem / 100.0)),
            disco_pct=round(disco, 1),
            disco_total_gb=disco_total,
            disco_usado_gb=round(disco_total * disco / 100.0, 1),
            uptime_segundos=uptime,
            carga1=round(max(0.0, cpu / 100.0 * dados["nucleos"] + rng.uniform(-0.3, 0.3)), 2),
            carga5=round(max(0.0, cpu / 100.0 * dados["nucleos"] * 0.9), 2),
            carga15=round(max(0.0, cpu / 100.0 * dados["nucleos"] * 0.8), 2),
            nucleos=dados["nucleos"],
            sistema="Linux 6.8.0-generic",
        )

    def _ajustar_status(
        self, servidor: ServidorVPS, dados: dict[str, Any], ultima: LeituraMetrica | None
    ) -> None:
        """Define ``ultimo_status``/``ultima_coleta_em`` coerentes com o perfil."""
        if dados["perfil"] == "offline":
            servidor.ultimo_status = ServidorVPS.Status.OFFLINE
        else:
            servidor.ultimo_status = ServidorVPS.Status.ONLINE
        if ultima is not None:
            servidor.ultima_coleta_em = ultima.coletado_em or timezone.now()
        servidor.save(update_fields=["ultimo_status", "ultima_coleta_em", "atualizado_em"])

    @staticmethod
    def _limitar(valor: float, minimo: float, maximo: float) -> float:
        return max(minimo, min(maximo, valor))

"""Registro do módulo de prospecção no núcleo (seções 6 e 7 da SPEC).

Define ``ModuloProspeccao`` (subclasse de ``ModuloBase``) e a registra no
``registro`` singleton. Fornece:

- ``itens_menu``: os itens de sidebar do módulo (Painel, Empresas, Conexões,
  Nova busca). O Painel é o dashboard do módulo (chave da Google Places API,
  IA e métricas do Google).
- ``contexto_dashboard``: preenche TODAS as chaves do painel (seção 7) a partir
  do banco, com queries eficientes e resilientes (qualquer falha -> ``{}``,
  deixando o núcleo aplicar seus defaults zerados).

Todos os textos vêm de ``apps/nucleo/textos.py`` (seção ``modulos.prospeccao``).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.prospeccao.modulo")

# Nº de pontos das séries do gráfico de linha do Card 1 (seção 7).
SEMANAS_SERIE = 8

# Meta padrão de qualificação (Card 5) quando não houver configuração dinâmica.
META_QUALIFICADAS = 30

_M = "modulos.prospeccao."


@registro.registrar
class ModuloProspeccao(ModuloBase):
    """Módulo de prospecção: painel, leads, conexões e buscas."""

    slug = "prospeccao"
    nome = texto(_M + "nome")
    icone = "prospeccao"
    ordem = 10
    descricao = texto(_M + "descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para o Painel (dashboard do módulo)."""
        return "prospeccao:painel"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        definicoes = [
            (texto(_M + "menu.painel"), "prospeccao:painel", "dashboard", {"prospeccao:painel"}),
            (
                texto(_M + "menu.empresas"),
                "prospeccao:lista",
                "empresa",
                {
                    "prospeccao:lista",
                    "prospeccao:detalhe",
                    "prospeccao:atualizar_google",
                    "prospeccao:diagnostico_ia",
                },
            ),
            (texto(_M + "menu.conexoes"), "prospeccao:conexoes", "conexoes", {"prospeccao:conexoes"}),
            (
                texto(_M + "menu.nova_busca"),
                "prospeccao:nova_busca",
                "buscas",
                {"prospeccao:nova_busca", "prospeccao:executar_busca"},
            ),
        ]
        itens: list[dict] = []
        for rotulo, nome_url, icone, rotas_ativas in definicoes:
            itens.append(
                {
                    "rotulo": rotulo,
                    "url": self._url_ou_hash(nome_url),
                    "icone": icone,
                    "ativo": rota_atual in rotas_ativas,
                }
            )
        return itens

    def contexto_dashboard(self, request) -> dict:
        """Preenche TODAS as chaves do painel (seção 7) a partir do banco.

        É resiliente: qualquer exceção resulta em ``{}`` e o núcleo aplica os
        defaults zerados, garantindo que o dashboard nunca quebre.
        """
        try:
            from django.db.models import Count

            from apps.prospeccao.models import (
                PROBLEMAS,
                ConfiguracaoProspeccao,
                Empresa,
                filtros_problema,
                rotulo_problema,
            )

            agora = timezone.now()
            config = ConfiguracaoProspeccao.obter()
            base = Empresa.objects.all()

            total_empresas = base.count()
            novas_semana = base.filter(criado_em__gt=agora - timedelta(days=7)).count()

            # -- Card 1: séries semanais + variação --------------------------
            serie_encontradas = self._serie_semanal(base, agora)
            serie_qualificadas = self._serie_semanal(
                base.filter(status_prospeccao=Empresa.Status.QUALIFICADA), agora
            )
            variacao_pct = self._variacao_semana(serie_encontradas)

            # -- Card 2: oportunidades (donut por tipo de problema) ----------
            filtros = filtros_problema(config)
            # Apelidos prefixados ("p_") para não colidir com nomes de campos.
            agregado = base.aggregate(
                **{f"p_{slug}": Count("pk", filter=filtros[slug]) for slug in PROBLEMAS}
            )
            contagem_problemas = {
                slug: int(agregado.get(f"p_{slug}") or 0) for slug in PROBLEMAS
            }
            oportunidades = self._montar_oportunidades(
                contagem_problemas, PROBLEMAS, rotulo_problema
            )
            oportunidades_total = sum(contagem_problemas.values())

            # -- Card 4: tabela principal (linhas EmpresaLinha) --------------
            recentes = list(base.order_by("-oportunidade_score", "-criado_em")[:8])
            empresas = [e.linha_dashboard(config) for e in recentes]

            # -- Card 3: próximas ações --------------------------------------
            proximas_acoes = self._montar_proximas_acoes(base, Empresa, config)

            # -- Card 5: meta de prospecção ----------------------------------
            qualificadas = base.filter(
                status_prospeccao=Empresa.Status.QUALIFICADA
            ).count()
            meta_total = META_QUALIFICADAS
            meta_atual = qualificadas
            meta_pct = self._percentual(meta_atual, meta_total)

            # -- Card 6: destaques -------------------------------------------
            destaque_titulo, destaque_texto = self._montar_destaque(recentes, config)

            return {
                "total_empresas": total_empresas,
                "novas_semana": novas_semana,
                "variacao_pct": variacao_pct,
                "serie_encontradas": serie_encontradas,
                "serie_qualificadas": serie_qualificadas,
                "oportunidades_total": oportunidades_total,
                "oportunidades": oportunidades,
                "proximas_acoes": proximas_acoes,
                "empresas": empresas,
                "meta_atual": meta_atual,
                "meta_total": meta_total,
                "meta_pct": meta_pct,
                "destaque_titulo": destaque_titulo,
                "destaque_texto": destaque_texto,
            }
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar contexto_dashboard da prospecção.")
            return {}

    def cards_resumo(self, request) -> list[dict]:
        """KPIs da prospecção para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from functools import reduce
            from operator import or_

            from apps.prospeccao.models import (
                PROBLEMAS_GOOGLE,
                ConfiguracaoProspeccao,
                Empresa,
                filtros_problema,
            )

            base = Empresa.objects.all()
            total = base.count()
            qualificadas = base.filter(
                status_prospeccao=Empresa.Status.QUALIFICADA
            ).count()
            com_oportunidade = base.filter(oportunidade_score__gte=70).count()
            filtros = filtros_problema(ConfiguracaoProspeccao.obter())
            alerta_google = reduce(or_, (filtros[slug] for slug in PROBLEMAS_GOOGLE))
            com_alerta_google = (
                base.filter(analisado_places_em__isnull=False).filter(alerta_google).count()
            )
            url_lista = self._url_ou_hash("prospeccao:lista")
            return [
                {
                    "rotulo": texto(_M + "cards.empresas_rotulo"),
                    "valor": total,
                    "detalhe": texto(_M + "cards.empresas_detalhe"),
                    "icone": "empresa",
                    "cor": "#7c5cff",
                    "url": url_lista,
                },
                {
                    "rotulo": texto(_M + "cards.alta_rotulo"),
                    "valor": com_oportunidade,
                    "detalhe": texto(_M + "cards.alta_detalhe"),
                    "icone": "prospeccao",
                    "cor": "#f87171",
                    "url": url_lista,
                },
                {
                    "rotulo": texto(_M + "cards.qualificadas_rotulo"),
                    "valor": qualificadas,
                    "detalhe": texto(_M + "cards.qualificadas_detalhe"),
                    "icone": "tarefa",
                    "cor": "#34d399",
                    "url": url_lista,
                },
                {
                    "rotulo": texto(_M + "cards.alertas_google_rotulo"),
                    "valor": com_alerta_google,
                    "detalhe": texto(_M + "cards.alertas_google_detalhe"),
                    "icone": "alerta",
                    "cor": "#fbbf24",
                    "url": self._url_ou_hash("prospeccao:painel"),
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo da prospecção.")
            return []

    # -- Auxiliares de menu -------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            logger.debug("URL '%s' não pôde ser resolvida.", nome_url)
            return "#"

    # -- Auxiliares de dashboard -------------------------------------------
    def _serie_semanal(self, queryset, agora) -> list[int]:
        """Conta os registros por janela semanal, do mais antigo ao mais recente."""
        pontos: list[int] = []
        for i in range(SEMANAS_SERIE - 1, -1, -1):
            inicio = agora - timedelta(weeks=i + 1)
            fim = agora - timedelta(weeks=i)
            pontos.append(queryset.filter(criado_em__gt=inicio, criado_em__lte=fim).count())
        return pontos

    def _variacao_semana(self, serie: list[int]) -> float:
        """Variação percentual entre a última e a penúltima semana da série."""
        if len(serie) < 2:
            return 0.0
        atual, anterior = serie[-1], serie[-2]
        if anterior == 0:
            return 100.0 if atual else 0.0
        return round((atual - anterior) / anterior * 100, 1)

    def _montar_oportunidades(self, contagem: dict[str, int], catalogo: dict, rotulo) -> list[dict]:
        """Converte contagens de problemas em fatias do donut (rotulo/pct/cor)."""
        total = sum(contagem.values())
        oportunidades: list[dict] = []
        for slug, quantidade in contagem.items():
            if quantidade <= 0:
                continue
            oportunidades.append(
                {
                    "rotulo": rotulo(slug),
                    "pct": self._percentual(quantidade, total),
                    "cor": catalogo.get(slug, ("", "#7c5cff"))[1],
                }
            )
        oportunidades.sort(key=lambda o: o["pct"], reverse=True)
        return oportunidades

    def _montar_proximas_acoes(self, base, modelo, config) -> list[dict]:
        """Sugere contatos com leads novos de maior oportunidade."""
        candidatas = base.filter(status_prospeccao=modelo.Status.NOVA).order_by(
            "-oportunidade_score", "-criado_em"
        )[:4]
        acoes: list[dict] = []
        for empresa in candidatas:
            problemas = empresa.rotulos_problemas(config)
            acoes.append(
                {
                    "quando": texto(_M + "acoes.prioritario")
                    if empresa.oportunidade_score >= 70
                    else texto(_M + "acoes.em_breve"),
                    "titulo": texto(_M + "acoes.contatar", nome=empresa.nome),
                    "tag": problemas[0] if problemas else texto(_M + "acoes.novo_lead"),
                }
            )
        return acoes

    def _montar_destaque(self, recentes: list, config) -> tuple[str, str]:
        """Destaca a empresa de maior oportunidade entre as recentes."""
        if not recentes:
            return "", ""
        melhor = max(recentes, key=lambda e: e.oportunidade_score)
        problemas = melhor.rotulos_problemas(config)
        resumo = ", ".join(problemas) if problemas else texto(_M + "destaque.sem_problemas")
        descricao = texto(
            _M + "destaque.texto",
            nome=melhor.nome,
            score=melhor.oportunidade_score,
            resumo=resumo,
        )
        return texto(_M + "destaque.titulo"), descricao

    def _percentual(self, parte: int, total: int) -> int:
        """Percentual inteiro (0..100) resiliente a divisão por zero."""
        if total <= 0:
            return 0
        return max(0, min(100, round(parte / total * 100)))

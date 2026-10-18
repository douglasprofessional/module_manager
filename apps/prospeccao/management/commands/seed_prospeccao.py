"""Comando ``seed_prospeccao``: popula o banco para demonstrar o dashboard.

Cria uma ``ConexaoGoogle`` demo, uma ``Busca`` concluída e ~8 ``Empresa``
fictícias (brasileiras, plausíveis) cobrindo TODOS os problemas: sem site,
site desatualizado, apenas Instagram, SEO fraco, performance baixa, sem SSL e
hospedagem sem site. As 7 colunas obrigatórias (seção 7) são preenchidas com
dados coerentes. Também preenche as métricas da Google Places API (nota,
avaliações, fotos, horário, situação e última atividade) e roda o motor de
análise para gerar diagnóstico e score. NÃO faz nenhuma chamada externa.

Idempotente: reexecutar atualiza os mesmos registros (chaveados por ``place_id``
``seed-XXXX`` e pelo nome da conexão/busca demo). As datas de criação são
espalhadas ao longo de ~8 semanas para dar forma às séries do gráfico.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.prospeccao.models import Busca, ConexaoGoogle, Empresa
from apps.prospeccao.services import orquestrador
from apps.prospeccao.services.analise_places import (
    HORARIO_AUSENTE,
    HORARIO_INCOMPLETO,
    HORARIO_OK,
    STATUS_FECHADA_PERMANENTEMENTE,
    STATUS_OPERACIONAL,
)

logger = logging.getLogger("modulos.prospeccao.seed")

NOME_CONEXAO_DEMO = "Conexão Demo"
CHAVE_DEMO = "AIzaSyDEMO-FICTICIA-SOMENTE-PARA-SEED"

# Empresas fictícias. 'dias_atras' espalha 'criado_em' pelas últimas ~8 semanas.
EMPRESAS_DEMO: list[dict[str, Any]] = [
    {
        "place_id": "seed-0001",
        "nome": "Padaria Pão Dourado",
        "categoria": "Padaria",
        "endereco": "Rua das Flores, 120 — Tijuca, Rio de Janeiro, RJ",
        "telefone": "+55 21 2555-1010",
        "whatsapp": "+55 21 98888-1010",
        "email": "",
        "instagram": "@paodouradorj",
        "website": "",
        "dominio": "",
        "tem_site": False,
        "site_desatualizado": False,
        "apenas_instagram": False,
        "tem_ssl": None,
        "hospedagem_sem_site": False,
        "score_seo": None,
        "score_performance": None,
        "responsavel": "Marta Coelho",
        "cargo_responsavel": "Proprietária",
        "tempo_mercado_texto": "18 anos",
        "data_fundacao": dt.date(2007, 3, 12),
        "status_prospeccao": Empresa.Status.NOVA,
        "oportunidade_score": 88,
        "dias_atras": 2,
    },
    {
        "place_id": "seed-0002",
        "nome": "Auto Peças Silva & Filhos",
        "categoria": "Autopeças",
        "endereco": "Av. Brasil, 4500 — Bonsucesso, Rio de Janeiro, RJ",
        "telefone": "+55 21 2233-4455",
        "whatsapp": "+55 21 97777-4455",
        "email": "contato@autopecassilva.com.br",
        "instagram": "@autopecassilva",
        "website": "http://www.autopecassilva.com.br",
        "dominio": "autopecassilva.com.br",
        "tem_site": True,
        "site_desatualizado": True,
        "apenas_instagram": False,
        "tem_ssl": True,
        "hospedagem_sem_site": False,
        "score_seo": 28,
        "score_performance": 54,
        "responsavel": "Jorge Silva",
        "cargo_responsavel": "Sócio-fundador",
        "tempo_mercado_texto": "Fundada em 2001",
        "data_fundacao": dt.date(2001, 8, 1),
        "status_prospeccao": Empresa.Status.NOVA,
        "oportunidade_score": 79,
        "dias_atras": 9,
    },
    {
        "place_id": "seed-0003",
        "nome": "Studio Bella Estética",
        "categoria": "Estética e beleza",
        "endereco": "Rua Visconde de Pirajá, 300 — Ipanema, Rio de Janeiro, RJ",
        "telefone": "",
        "whatsapp": "+55 21 96666-2020",
        "email": "studiobella@gmail.com",
        "instagram": "@studiobellaestetica",
        "website": "",
        "dominio": "",
        "tem_site": False,
        "site_desatualizado": False,
        "apenas_instagram": True,
        "tem_ssl": None,
        "hospedagem_sem_site": False,
        "score_seo": None,
        "score_performance": None,
        "responsavel": "Beatriz Nunes",
        "cargo_responsavel": "Proprietária",
        "tempo_mercado_texto": "6 anos",
        "data_fundacao": dt.date(2019, 5, 20),
        "status_prospeccao": Empresa.Status.NOVA,
        "oportunidade_score": 84,
        "dias_atras": 16,
    },
    {
        "place_id": "seed-0004",
        "nome": "Marcenaria Souza Móveis",
        "categoria": "Marcenaria",
        "endereco": "Estrada do Galeão, 1200 — Ilha do Governador, Rio de Janeiro, RJ",
        "telefone": "+55 21 2444-3322",
        "whatsapp": "+55 21 95555-3322",
        "email": "orcamento@marcenariasouza.com.br",
        "instagram": "@marcenariasouza",
        "website": "https://www.marcenariasouza.com.br",
        "dominio": "marcenariasouza.com.br",
        "tem_site": True,
        "site_desatualizado": False,
        "apenas_instagram": False,
        "tem_ssl": True,
        "hospedagem_sem_site": False,
        "score_seo": 35,
        "score_performance": 72,
        "responsavel": "Antônio Souza",
        "cargo_responsavel": "Fundador",
        "tempo_mercado_texto": "22 anos",
        "data_fundacao": dt.date(2003, 2, 10),
        "status_prospeccao": Empresa.Status.QUALIFICADA,
        "oportunidade_score": 61,
        "dias_atras": 24,
    },
    {
        "place_id": "seed-0005",
        "nome": "Restaurante Sabor Caseiro",
        "categoria": "Restaurante",
        "endereco": "Rua do Catete, 88 — Catete, Rio de Janeiro, RJ",
        "telefone": "+55 21 2225-7788",
        "whatsapp": "+55 21 94444-7788",
        "email": "reservas@saborcaseiro.com.br",
        "instagram": "@saborcaseirorj",
        "website": "https://www.saborcaseiro.com.br",
        "dominio": "saborcaseiro.com.br",
        "tem_site": True,
        "site_desatualizado": False,
        "apenas_instagram": False,
        "tem_ssl": True,
        "hospedagem_sem_site": False,
        "score_seo": 65,
        "score_performance": 32,
        "responsavel": "Cláudia Ramos",
        "cargo_responsavel": "Gerente",
        "tempo_mercado_texto": "11 anos",
        "data_fundacao": dt.date(2014, 9, 5),
        "status_prospeccao": Empresa.Status.NOVA,
        "oportunidade_score": 67,
        "dias_atras": 31,
    },
    {
        "place_id": "seed-0006",
        "nome": "Clínica OdontoVida",
        "categoria": "Clínica odontológica",
        "endereco": "Av. Nossa Sra. de Copacabana, 700 — Copacabana, Rio de Janeiro, RJ",
        "telefone": "+55 21 2547-9090",
        "whatsapp": "+55 21 93333-9090",
        "email": "atendimento@odontovida.com.br",
        "instagram": "@odontovidarj",
        "website": "http://www.odontovida.com.br",
        "dominio": "odontovida.com.br",
        "tem_site": True,
        "site_desatualizado": False,
        "apenas_instagram": False,
        "tem_ssl": False,
        "hospedagem_sem_site": False,
        "score_seo": 58,
        "score_performance": 61,
        "responsavel": "Dr. Ricardo Alves",
        "cargo_responsavel": "Diretor clínico",
        "tempo_mercado_texto": "Fundada em 2016",
        "data_fundacao": dt.date(2016, 1, 18),
        "status_prospeccao": Empresa.Status.CONTATADA,
        "oportunidade_score": 71,
        "dias_atras": 38,
    },
    {
        "place_id": "seed-0007",
        "nome": "Transportadora RápidoLog",
        "categoria": "Transporte e logística",
        "endereco": "Rod. Washington Luiz, km 15 — Duque de Caxias, RJ",
        "telefone": "+55 21 2671-1234",
        "whatsapp": "+55 21 92222-1234",
        "email": "comercial@rapidolog.com.br",
        "instagram": "@rapidolog",
        "website": "",
        "dominio": "rapidolog.com.br",
        "tem_site": False,
        "site_desatualizado": False,
        "apenas_instagram": False,
        "tem_ssl": None,
        "hospedagem_sem_site": True,
        "score_seo": None,
        "score_performance": None,
        "responsavel": "Fernanda Lima",
        "cargo_responsavel": "Diretora comercial",
        "tempo_mercado_texto": "9 anos",
        "data_fundacao": dt.date(2016, 6, 30),
        "status_prospeccao": Empresa.Status.NOVA,
        "oportunidade_score": 75,
        "dias_atras": 45,
    },
    {
        "place_id": "seed-0008",
        "nome": "Boutique Elegance Moda",
        "categoria": "Moda e vestuário",
        "endereco": "Rua Dias Ferreira, 45 — Leblon, Rio de Janeiro, RJ",
        "telefone": "+55 21 2512-6060",
        "whatsapp": "+55 21 91111-6060",
        "email": "contato@boutiqueelegance.com.br",
        "instagram": "@boutiqueelegancerj",
        "website": "https://www.boutiqueelegance.com.br",
        "dominio": "boutiqueelegance.com.br",
        "tem_site": True,
        "site_desatualizado": True,
        "apenas_instagram": False,
        "tem_ssl": True,
        "hospedagem_sem_site": False,
        "score_seo": 52,
        "score_performance": 40,
        "responsavel": "Patrícia Moreira",
        "cargo_responsavel": "Proprietária",
        "tempo_mercado_texto": "13 anos",
        "data_fundacao": dt.date(2012, 11, 3),
        "status_prospeccao": Empresa.Status.QUALIFICADA,
        "oportunidade_score": 59,
        "dias_atras": 52,
    },
]


# Horário de exemplo (descrições da semana, como a Places API devolve).
_SEMANA_COMERCIAL = [
    "segunda-feira: 08:00–18:00",
    "terça-feira: 08:00–18:00",
    "quarta-feira: 08:00–18:00",
    "quinta-feira: 08:00–18:00",
    "sexta-feira: 08:00–18:00",
    "sábado: 08:00–12:00",
    "domingo: Fechado",
]

# Métricas da Google Places API por empresa demo. 'dias_atividade' = dias desde
# a avaliação mais recente (None = sem avaliações datadas).
SINAIS_GOOGLE_DEMO: dict[str, dict[str, Any]] = {
    "seed-0001": {"nota_google": 4.6, "total_avaliacoes": 132, "total_fotos": 10, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_OK, "dias_atividade": 10},
    "seed-0002": {"nota_google": 3.7, "total_avaliacoes": 18, "total_fotos": 2, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_INCOMPLETO, "dias_atividade": 200},
    "seed-0003": {"nota_google": 4.2, "total_avaliacoes": 3, "total_fotos": 0, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_AUSENTE, "dias_atividade": None},
    "seed-0004": {"nota_google": 4.8, "total_avaliacoes": 54, "total_fotos": 8, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_OK, "dias_atividade": 30},
    "seed-0005": {"nota_google": 3.2, "total_avaliacoes": 9, "total_fotos": 4, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_OK, "dias_atividade": 400},
    "seed-0006": {"nota_google": 4.4, "total_avaliacoes": 41, "total_fotos": 6, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_OK, "dias_atividade": 45},
    "seed-0007": {"nota_google": None, "total_avaliacoes": 0, "total_fotos": 1, "status_google": STATUS_FECHADA_PERMANENTEMENTE, "situacao_horario": HORARIO_AUSENTE, "dias_atividade": None},
    "seed-0008": {"nota_google": 4.5, "total_avaliacoes": 76, "total_fotos": 10, "status_google": STATUS_OPERACIONAL, "situacao_horario": HORARIO_OK, "dias_atividade": 5},
}


def _sinais_google(place_id: str, agora) -> dict[str, Any]:
    """Campos de métricas do Google da empresa demo (ou {} se não houver)."""
    sinais = dict(SINAIS_GOOGLE_DEMO.get(place_id) or {})
    if not sinais:
        return {}
    dias = sinais.pop("dias_atividade")
    sinais["ultima_atividade_perfil"] = (
        timezone.localdate() - dt.timedelta(days=dias) if dias is not None else None
    )
    sinais["horario_semana"] = list(_SEMANA_COMERCIAL) if sinais["situacao_horario"] == HORARIO_OK else []
    sinais["google_maps_url"] = f"https://maps.google.com/?cid={place_id}"
    sinais["analisado_places_em"] = agora
    return sinais


class Command(BaseCommand):
    """Popula o banco com dados de demonstração da prospecção (sem rede)."""

    help = "Cria conexão demo, uma busca concluída e empresas fictícias de exemplo."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        usuario = self._obter_usuario()

        conexao = self._criar_conexao(usuario)
        busca = self._criar_busca(conexao, usuario)
        criadas = self._criar_empresas(busca)

        # Atualiza o total da busca com o número real de empresas vinculadas.
        Busca.objects.filter(pk=busca.pk).update(total_resultados=criadas)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed concluído: conexão '{conexao.nome}', "
                f"1 busca e {criadas} empresa(s)."
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
                    "Nenhum usuário admin encontrado; os registros ficam sem 'criado_por'."
                )
            )
        return usuario

    def _criar_conexao(self, usuario) -> ConexaoGoogle:
        conexao, _criada = ConexaoGoogle.objects.get_or_create(
            nome=NOME_CONEXAO_DEMO,
            defaults={"ativo": True, "criado_por": usuario},
        )
        # Garante uma chave (cifrada) sempre presente, sem depender de rede.
        if not conexao.tem_chave:
            conexao.chave_api = CHAVE_DEMO
        conexao.ativo = True
        if usuario is not None and conexao.criado_por_id is None:
            conexao.criado_por = usuario
        conexao.save()
        return conexao

    def _criar_busca(self, conexao: ConexaoGoogle, usuario) -> Busca:
        busca, _criada = Busca.objects.get_or_create(
            conexao=conexao,
            termo="comércios e serviços",
            localizacao="Rio de Janeiro, RJ",
            defaults={
                "raio_metros": 5000,
                "status": Busca.Status.CONCLUIDA,
                "criado_por": usuario,
            },
        )
        busca.status = Busca.Status.CONCLUIDA
        if usuario is not None and busca.criado_por_id is None:
            busca.criado_por = usuario
        busca.save()
        return busca

    def _criar_empresas(self, busca: Busca) -> int:
        agora = timezone.now()
        total = 0
        for dados in EMPRESAS_DEMO:
            dados = dict(dados)  # cópia rasa: não mutar a constante
            place_id = dados.pop("place_id")
            dias_atras = dados.pop("dias_atras")
            dados["busca"] = busca
            dados.update(_sinais_google(place_id, agora))

            empresa, _criada = Empresa.objects.update_or_create(
                place_id=place_id, defaults=dados
            )

            # Espalha 'criado_em' (auto_now_add) via update() para moldar as séries.
            quando = agora - dt.timedelta(days=dias_atras)
            Empresa.objects.filter(pk=empresa.pk).update(criado_em=quando)

            # Motor de análise: diagnóstico e score a partir das métricas demo.
            orquestrador.recalcular_empresa(empresa)
            total += 1

        return total

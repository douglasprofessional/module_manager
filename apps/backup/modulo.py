"""Registro do módulo de backup no núcleo (adendo 2 — MÓDULO 4).

Define ``ModuloBackup`` (subclasse de ``ModuloBase``) e a registra no
``registro`` singleton. Fornece:

- ``itens_menu``: um item de sidebar ("Backup").
- ``cards_resumo``: 2 KPIs (nº de backups concluídos e o último gerado).
- ``contexto_dashboard``: ``{}`` (o painel principal é da prospecção).
"""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.nucleo.modulos import ModuloBase, registro
from apps.nucleo.textos import texto

logger = logging.getLogger("modulos.backup.modulo")


@registro.registrar
class ModuloBackup(ModuloBase):
    """Módulo de backup: gera backups por módulo (fixtures) e completos."""

    slug = "backup"
    nome = texto("modulos.backup.nome")
    icone = "backup"
    ordem = 50
    descricao = texto("modulos.backup.descricao")

    def url_inicial(self) -> str:
        """Item principal do módulo aponta para a lista de backups."""
        return "backup:lista"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar do módulo (chaves EXATAS de ``ItemMenu``)."""
        rota_atual = self._rota_atual(request)
        return [
            {
                "rotulo": texto("modulos.backup.menu.backup"),
                "url": self._url_ou_hash("backup:lista"),
                "icone": "backup",
                "ativo": rota_atual in {"backup:lista", "backup:novo"},
            }
        ]

    def cards_resumo(self, request) -> list[dict]:
        """KPIs de backup para a faixa de resumo do dashboard.

        Resiliente: qualquer falha resulta em lista vazia (o dashboard segue).
        """
        try:
            from apps.backup.models import Backup

            concluidos = Backup.objects.filter(status=Backup.Status.CONCLUIDO)
            total = concluidos.count()

            ultimo = concluidos.order_by("-concluido_em", "-criado_em").first()
            if ultimo is not None:
                quando = ultimo.concluido_em or ultimo.criado_em
                valor = timezone.localtime(quando).strftime("%d/%m %H:%M") if quando else "—"
                detalhe = ultimo.rotulo or ultimo.escopo
            else:
                valor = "—"
                detalhe = texto("modulos.backup.cards.ultimo_vazio")

            url_lista = self._url_ou_hash("backup:lista")
            return [
                {
                    "rotulo": texto("modulos.backup.cards.backups_rotulo"),
                    "valor": total,
                    "detalhe": texto("modulos.backup.cards.backups_detalhe"),
                    "icone": "backup",
                    "cor": "#7c5cff",
                    "url": url_lista,
                },
                {
                    "rotulo": texto("modulos.backup.cards.ultimo_rotulo"),
                    "valor": valor,
                    "detalhe": detalhe,
                    "icone": "atualizar",
                    "cor": "#34d399",
                    "url": url_lista,
                },
            ]
        except Exception:  # pragma: no cover - dashboard nunca quebra por um módulo
            logger.exception("Falha ao montar cards_resumo do backup.")
            return []

    def contexto_dashboard(self, request) -> dict:
        """O painel principal é da prospecção; este módulo não injeta dados."""
        return {}

    def excluir_dados(self, request) -> int:
        """Exclui os REGISTROS de backup e os ARQUIVOS correspondentes no disco.

        Remove só arquivos contidos em ``BACKUPS_DIR`` (defensivo, via
        ``Backup.existe()``). Retorna a quantidade de registros removidos.
        """
        try:
            from apps.backup.models import Backup

            registros = list(Backup.objects.all())
            for backup in registros:
                try:
                    if backup.existe():
                        backup.caminho_absoluto().unlink(missing_ok=True)
                except OSError:
                    logger.warning("Falha ao remover arquivo do backup %s.", backup.pk)
            total = Backup.objects.all().delete()[0]
            return total
        except Exception:  # pragma: no cover - resiliência
            logger.exception("Falha ao excluir dados do módulo de backup.")
            return 0

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

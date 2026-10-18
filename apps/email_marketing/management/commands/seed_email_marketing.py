"""Comando ``seed_email_marketing``: popula o módulo para demonstração.

Cria, de forma IDEMPOTENTE e SEM qualquer acesso de rede:

- 1 ``ConfiguracaoEnvio`` do tipo CONSOLE ("Remetente de Teste (Console)") com
  ``email_remetente`` ``no-reply@modulos.local``. Com o backend de console, o
  envio em massa IMPRIME o e-mail no stdout/log — dá para testar o disparo
  localmente sem um SMTP real.
- ~6 ``Contato`` fictícios (inscritos).
- 1 ``Lista`` "Clientes (demo)" com esses contatos.
- 1 ``Campanha`` em RASCUNHO ("Novidades de {mês}") usando ``{{ nome }}`` e
  ``{{ link_descadastro }}`` no corpo. NÃO é enviada (fica em rascunho).

``get_or_create`` por chaves naturais (e-mail / nome). Reexecutar não duplica.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.email_marketing.models import Campanha, ConfiguracaoEnvio, Contato, Lista

logger = logging.getLogger("modulos.email_marketing.seed")

# Meses em PT-BR (para o nome da campanha demo).
MESES_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

NOME_CONFIG = "Remetente de Teste (Console)"
NOME_LISTA = "Clientes (demo)"

# Contatos fictícios (e-mails de exemplo com domínio de documentação .example).
CONTATOS_DEMO: list[dict[str, str]] = [
    {"email": "maria.souza@exemplo.example", "nome": "Maria Souza", "empresa": "Padaria da Praça"},
    {"email": "joao.lima@exemplo.example", "nome": "João Lima", "empresa": "Auto Peças Lima"},
    {"email": "ana.paula@exemplo.example", "nome": "Ana Paula", "empresa": "Studio Ana Paula"},
    {"email": "carlos.mendes@exemplo.example", "nome": "Carlos Mendes", "empresa": "Mendes Contabilidade"},
    {"email": "fernanda.rocha@exemplo.example", "nome": "Fernanda Rocha", "empresa": "Rocha Advocacia"},
    {"email": "bruno.alves@exemplo.example", "nome": "Bruno Alves", "empresa": "Alves Marcenaria"},
]

CORPO_HTML_DEMO = """<p>Olá, {{ nome }}!</p>
<p>Temos novidades preparadas especialmente para a {{ empresa }}. Aproveite as
condições deste mês e fale com a nossa equipe.</p>
<p>Um abraço,<br>Equipe modulos</p>
<hr>
<p style="font-size:12px;color:#888">
  Se não quiser mais receber nossos e-mails,
  <a href="{{ link_descadastro }}">descadastre-se aqui</a>.
</p>"""

CORPO_TEXTO_DEMO = (
    "Olá, {{ nome }}!\n\n"
    "Temos novidades preparadas especialmente para a {{ empresa }}. "
    "Aproveite as condições deste mês e fale com a nossa equipe.\n\n"
    "Um abraço,\nEquipe modulos\n\n"
    "Para não receber mais nossos e-mails, acesse: {{ link_descadastro }}"
)


class Command(BaseCommand):
    """Popula o módulo com config CONSOLE, contatos, lista e campanha (rascunho)."""

    help = "Cria dados demo do marketing por e-mail (config CONSOLE, contatos, lista, campanha)."

    def handle(self, *args: Any, **opcoes: Any) -> None:
        usuario = self._obter_usuario()

        configuracao = self._criar_configuracao(usuario)
        contatos = self._criar_contatos()
        lista = self._criar_lista(contatos)
        campanha = self._criar_campanha(configuracao, lista, usuario)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed de marketing por e-mail concluído: "
                f"1 configuração ({configuracao.get_tipo_display()}), "
                f"{len(contatos)} contato(s), 1 lista e "
                f"1 campanha em rascunho ('{campanha.nome}')."
            )
        )

    # -- Passos -------------------------------------------------------------
    def _obter_usuario(self):
        """Retorna um usuário admin existente (ou ``None``; os FKs são opcionais)."""
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

    def _criar_configuracao(self, usuario) -> ConfiguracaoEnvio:
        configuracao, _criada = ConfiguracaoEnvio.objects.get_or_create(
            nome=NOME_CONFIG,
            defaults={
                "tipo": ConfiguracaoEnvio.Tipo.CONSOLE,
                "email_remetente": "no-reply@modulos.local",
                "nome_remetente": "modulos (Teste)",
                "ativo": True,
                "criado_por": usuario,
            },
        )
        # Mantém coerente ao reexecutar (é uma config de teste, sem SMTP/segredos).
        configuracao.tipo = ConfiguracaoEnvio.Tipo.CONSOLE
        configuracao.email_remetente = "no-reply@modulos.local"
        configuracao.nome_remetente = "modulos (Teste)"
        configuracao.ativo = True
        if usuario is not None and configuracao.criado_por_id is None:
            configuracao.criado_por = usuario
        configuracao.save()
        return configuracao

    def _criar_contatos(self) -> list[Contato]:
        contatos: list[Contato] = []
        for dados in CONTATOS_DEMO:
            contato, _criado = Contato.objects.get_or_create(
                email=dados["email"],
                defaults={
                    "nome": dados["nome"],
                    "empresa": dados["empresa"],
                    "inscrito": True,
                    "origem": "seed",
                },
            )
            contatos.append(contato)
        return contatos

    def _criar_lista(self, contatos: list[Contato]) -> Lista:
        lista, _criada = Lista.objects.get_or_create(
            nome=NOME_LISTA,
            defaults={"descricao": "Lista de demonstração criada pelo seed."},
        )
        # Garante que os contatos demo estejam na lista (idempotente).
        lista.contatos.set(contatos)
        return lista

    def _criar_campanha(self, configuracao, lista, usuario) -> Campanha:
        mes = MESES_PT[timezone.localtime(timezone.now()).month - 1]
        nome = f"Novidades de {mes}"
        campanha, _criada = Campanha.objects.get_or_create(
            nome=nome,
            defaults={
                "assunto": "{{ nome }}, temos novidades para você",
                "corpo_html": CORPO_HTML_DEMO,
                "corpo_texto": CORPO_TEXTO_DEMO,
                "configuracao": configuracao,
                "lista": lista,
                "status": Campanha.Status.RASCUNHO,
                "criado_por": usuario,
            },
        )
        return campanha

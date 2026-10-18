"""Serviço de envio de e-mail (adendo 3 — MÓDULO 5) — o CORAÇÃO da solução.

SEGURANÇA CRÍTICA (seção 9 da SPEC + checklist do adendo):

- Solução AUTOCONTIDA: a conexão vem de ``configuracao.abrir_conexao()`` (SMTP ou
  Console do PRÓPRIO módulo), nunca das configs globais ``EMAIL_*`` do Django.
- O corpo é renderizado por ``str.replace`` dos marcadores — SEM o motor de
  template do Django (evita SSTI). No corpo HTML, os valores do contato são
  ESCAPADOS com ``django.utils.html.escape`` (evita injeção de HTML a partir de
  dados do contato). O ``link_descadastro`` é uma URL gerada por nós (token
  URL-safe), inserida como está.
- Envio RESILIENTE por destinatário: a falha de um e-mail não interrompe os
  demais; cada resultado vira um ``EnvioEmail`` (log) e alimenta os contadores.
- A conexão é sempre fechada no ``finally``.
- A senha SMTP NUNCA aparece em log ou em mensagem de exceção (mensagens
  genéricas por tipo de erro).

Observação de escala: o envio é SÍNCRONO (roda no request), isolado e pronto
para Celery. Listas muito grandes devem, no futuro, usar um worker/tarefa
assíncrona para não bloquear o request nem estourar timeouts.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

logger = logging.getLogger("modulos.email_marketing.enviador")

# Marcadores aceitos na personalização (com e sem espaços internos).
MARCADORES = ("nome", "email", "empresa", "link_descadastro")


def _intervalo_entre_envios() -> float:
    """Segundos a aguardar entre envios (rate limiting anti-spam).

    Lê ``settings.EMAIL_MARKETING_RATE_LIMIT`` (e-mails por minuto; 0 = sem
    limite). Enviar em rajada é um forte sinal de spam para Gmail/Hotmail;
    um limite modesto (ex.: 60/min) melhora a entregabilidade e evita bloqueios
    temporários do provedor SMTP.
    """
    try:
        rate = int(getattr(settings, "EMAIL_MARKETING_RATE_LIMIT", 0) or 0)
    except (TypeError, ValueError):
        rate = 0
    return (60.0 / rate) if rate > 0 else 0.0


def _cabecalhos_antispam(link_descadastro: str) -> dict:
    """Cabeçalhos que melhoram a entregabilidade (RFC 2369 / RFC 8058).

    - ``List-Unsubscribe``: expõe o link de descadastro ao cliente de e-mail
      (Gmail/Outlook mostram o botão nativo "Cancelar inscrição").
    - ``List-Unsubscribe-Post``: habilita o descadastro em UM clique (one-click)
      — o provedor faz um POST para o link. O endpoint público aceita esse POST
      (autenticado pelo token) sem exigir CSRF.
    """
    if not link_descadastro:
        return {}
    return {
        "List-Unsubscribe": f"<{link_descadastro}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def render_personalizado(texto: str, contato, link_descadastro: str, html: bool) -> str:
    """Substitui os marcadores por dados do contato via ``str.replace`` simples.

    Aceita ``{{ nome }}`` e ``{{nome}}`` (com e sem espaços). Marcadores
    suportados: ``nome``, ``email``, ``empresa`` e ``link_descadastro``.

    Quando ``html=True``, os valores do contato são escapados com
    ``django.utils.html.escape`` (segurança: dados do contato não podem quebrar
    nem injetar HTML). O ``link_descadastro`` é uma URL nossa e entra como está.

    NÃO usa o motor de template do Django (evita SSTI): apenas ``replace``.
    """
    texto = texto or ""

    nome = contato.nome or contato.primeiro_nome()
    email = contato.email or ""
    empresa = contato.empresa or ""
    if html:
        nome = escape(nome)
        email = escape(email)
        empresa = escape(empresa)

    substituicoes = {
        "nome": nome,
        "email": email,
        "empresa": empresa,
        "link_descadastro": link_descadastro or "",
    }
    for marcador, valor in substituicoes.items():
        texto = texto.replace("{{ %s }}" % marcador, valor)
        texto = texto.replace("{{%s}}" % marcador, valor)
    return texto


def _mensagem_erro(exc: Exception) -> str:
    """Mapeia uma exceção para uma mensagem GENÉRICA e segura (sem segredos)."""
    import smtplib
    import socket

    nome = type(exc).__name__
    if isinstance(exc, smtplib.SMTPAuthenticationError) or nome == "SMTPAuthenticationError":
        return "falha de autenticação SMTP"
    if isinstance(exc, smtplib.SMTPRecipientsRefused) or nome == "SMTPRecipientsRefused":
        return "destinatário recusado pelo servidor"
    if isinstance(exc, smtplib.SMTPSenderRefused) or nome == "SMTPSenderRefused":
        return "remetente recusado pelo servidor"
    if isinstance(exc, (socket.timeout,)) or nome == "timeout":
        return "tempo de conexão esgotado"
    if isinstance(exc, (ConnectionError, socket.gaierror)) or nome in (
        "gaierror",
        "SMTPConnectError",
        "SMTPServerDisconnected",
    ):
        return "não foi possível conectar ao servidor SMTP"
    if isinstance(exc, smtplib.SMTPException):
        return "falha no envio SMTP"
    return "falha ao enviar"


def _link_descadastro(contato) -> str:
    """Monta o link ABSOLUTO de descadastro público a partir de ``SITE_URL``."""
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    caminho = reverse("email_marketing:descadastrar", args=[contato.token_descadastro])
    return f"{base}{caminho}"


def enviar_teste(configuracao, destinatario: str) -> tuple[bool, str]:
    """Envia UM e-mail de teste pela ``configuracao``. Nunca lança; nunca loga senha.

    Retorna ``(ok, mensagem)``. Útil para validar o remetente/SMTP (ou ver o
    e-mail no log, no tipo Console) antes de disparar uma campanha.
    """
    conexao = None
    try:
        conexao = configuracao.abrir_conexao()
        assunto = f"Teste de envio — {configuracao.nome}"
        corpo = (
            "Este é um e-mail de teste do módulo de Marketing por E-mail do "
            "modulos. Se você recebeu esta mensagem, o remetente está "
            "configurado corretamente."
        )
        mensagem = EmailMultiAlternatives(
            assunto,
            corpo,
            from_email=configuracao.remetente_formatado(),
            to=[destinatario],
            reply_to=[configuracao.responder_para] if configuracao.responder_para else None,
            connection=conexao,
        )
        mensagem.send()
        return True, f"E-mail de teste enviado para {destinatario}."
    except Exception as exc:  # noqa: BLE001 - resiliência: nunca vaza segredo
        logger.warning(
            "Falha no envio de teste da configuração %s (%s).",
            getattr(configuracao, "pk", "?"),
            type(exc).__name__,
        )
        return False, f"Falha ao enviar o e-mail de teste: {_mensagem_erro(exc)}."
    finally:
        if conexao is not None:
            try:
                conexao.close()
            except Exception:  # pragma: no cover - fechamento best-effort
                pass


def enviar_campanha(campanha) -> dict:
    """Envia uma campanha em massa de forma resiliente por destinatário.

    Passos:
    1. valida ``pode_enviar()``; senão retorna erro de estado;
    2. marca ``ENVIANDO`` e zera contadores;
    3. abre a conexão da configuração da campanha (uma só, reaproveitada);
    4. para cada destinatário: renderiza assunto/texto/HTML personalizados, envia
       e registra um ``EnvioEmail`` (ENVIADO/FALHA), atualizando os contadores;
    5. fecha a conexão no ``finally``;
    6. grava o status final (ENVIADA / PARCIAL / ERRO) e os contadores.

    Retorna um resumo (dict) SEM segredos. Nunca loga a senha SMTP.
    """
    from apps.email_marketing.models import Campanha, EnvioEmail

    if not campanha.pode_enviar():
        return {
            "ok": False,
            "erro": "estado inválido",
            "status": campanha.status,
            "total": 0,
            "enviados": 0,
            "falhas": 0,
        }

    configuracao = campanha.configuracao

    # Marca em progresso e zera contadores antes de começar.
    campanha.status = Campanha.Status.ENVIANDO
    campanha.total_destinatarios = 0
    campanha.total_enviados = 0
    campanha.total_falhas = 0
    campanha.save(
        update_fields=[
            "status",
            "total_destinatarios",
            "total_enviados",
            "total_falhas",
        ]
    )

    destinatarios = list(campanha.destinatarios())
    total = len(destinatarios)
    enviados = 0
    falhas = 0
    erro_geral = False

    conexao = None
    try:
        conexao = configuracao.abrir_conexao()
        # Abre a conexão UMA vez e a reaproveita em todos os envios do lote: assim
        # cada ``msg.send()`` reutiliza o mesmo socket SMTP em vez de reabrir por
        # destinatário. No backend Console isto é um no-op. Fechada no ``finally``.
        conexao.open()
        remetente = configuracao.remetente_formatado()
        reply_to = [configuracao.responder_para] if configuracao.responder_para else None
        corpo_texto_base = campanha.corpo_texto_efetivo()
        intervalo = _intervalo_entre_envios()

        for indice, contato in enumerate(destinatarios):
            link = _link_descadastro(contato)
            assunto = render_personalizado(campanha.assunto, contato, link, html=False)
            texto = render_personalizado(corpo_texto_base, contato, link, html=False)
            corpo_html = render_personalizado(campanha.corpo_html, contato, link, html=True)
            try:
                mensagem = EmailMultiAlternatives(
                    assunto,
                    texto,
                    from_email=remetente,
                    to=[contato.email],
                    reply_to=reply_to,
                    connection=conexao,
                    headers=_cabecalhos_antispam(link),
                )
                mensagem.attach_alternative(corpo_html, "text/html")
                mensagem.send()
                EnvioEmail.objects.create(
                    campanha=campanha,
                    contato=contato,
                    email=contato.email,
                    status=EnvioEmail.Status.ENVIADO,
                    enviado_em=timezone.now(),
                )
                enviados += 1
                # Rate limiting anti-spam entre envios (não após o último).
                if intervalo and indice < total - 1:
                    time.sleep(intervalo)
            except Exception as exc:  # noqa: BLE001 - resiliente por destinatário
                logger.warning(
                    "Falha ao enviar para um destinatário da campanha %s (%s).",
                    campanha.pk,
                    type(exc).__name__,
                )
                EnvioEmail.objects.create(
                    campanha=campanha,
                    contato=contato,
                    email=contato.email,
                    status=EnvioEmail.Status.FALHA,
                    erro=_mensagem_erro(exc)[:255],
                )
                falhas += 1
    except Exception as exc:  # noqa: BLE001 - falha geral (ex.: abrir conexão)
        erro_geral = True
        logger.warning(
            "Falha geral ao enviar a campanha %s (%s).",
            campanha.pk,
            type(exc).__name__,
        )
    finally:
        if conexao is not None:
            try:
                conexao.close()
            except Exception:  # pragma: no cover - fechamento best-effort
                pass

    campanha.total_destinatarios = total
    campanha.total_enviados = enviados
    campanha.total_falhas = falhas

    # Sem destinatários: nada foi enviado. Mantém a campanha REENVIÁVEL (volta a
    # rascunho) e NÃO marca data de envio — evita o estado enganoso "Enviada" com
    # 0 e-mails, que ainda travaria o reenvio após adicionar contatos.
    if total == 0:
        campanha.status = Campanha.Status.RASCUNHO
        campanha.save(
            update_fields=[
                "status",
                "total_destinatarios",
                "total_enviados",
                "total_falhas",
            ]
        )
        return {
            "ok": False,
            "erro": "sem destinatários",
            "status": campanha.status,
            "total": 0,
            "enviados": 0,
            "falhas": 0,
        }

    # Com destinatários: ERRO se nenhum saiu (falha geral OU todas as falhas),
    # ENVIADA se todas saíram, PARCIAL se algumas falharam.
    if enviados == 0:
        status_final = Campanha.Status.ERRO
    elif falhas == 0:
        status_final = Campanha.Status.ENVIADA
    else:
        status_final = Campanha.Status.PARCIAL

    campanha.status = status_final
    campanha.enviada_em = timezone.now()
    campanha.save(
        update_fields=[
            "status",
            "total_destinatarios",
            "total_enviados",
            "total_falhas",
            "enviada_em",
        ]
    )

    return {
        "ok": enviados > 0,
        "status": status_final,
        "total": total,
        "enviados": enviados,
        "falhas": falhas,
    }

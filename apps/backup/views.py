"""Views do módulo de backup (adendo 2 — MÓDULO 4).

Todas exigem administrador (``is_staff``): a CBV via ``AdminRequeridoMixin`` e as
FBVs via ``@admin_requerido`` (defesa em profundidade — o
``SomenteAdminMiddleware`` já protege o site inteiro). As ações que alteram
dados/arquivos usam ``@csrf_protect`` + ``@require_POST`` e registram auditoria.

- ``BackupListView``: lista paginada dos backups gerados.
- ``novo``: escolhe tipo/escopo/mídia e executa o serviço SINCRONAMENTE.
- ``baixar`` (GET): download via ``FileResponse`` com validação anti path
  traversal (o caminho resolvido tem de estar dentro de ``BACKUPS_DIR``).
- ``excluir`` (POST): apaga o arquivo (só dentro de ``BACKUPS_DIR``) e o registro.

NÃO há restauração pela UI (perigosa): a restauração é feita por CLI
(``loaddata`` para fixtures) — documentada no README.
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import QuerySet
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import ListView

from apps.backup.forms import BackupForm
from apps.backup.models import Backup
from apps.backup.services import backup_service
from apps.contas.decorators import admin_requerido
from apps.contas.mixins import AdminRequeridoMixin

logger = logging.getLogger("modulos.backup.views")


def _ip(request: HttpRequest) -> str | None:
    """IP do cliente (REMOTE_ADDR); não confia em cabeçalhos de proxy."""
    return request.META.get("REMOTE_ADDR") or None


def _auditar(request: HttpRequest, acao: str, objeto: str = "") -> None:
    """Registra um evento de auditoria sem nunca quebrar o fluxo da view."""
    try:
        from apps.nucleo.models import RegistroAuditoria

        usuario = request.user if getattr(request.user, "is_authenticated", False) else None
        RegistroAuditoria.objects.create(
            usuario=usuario,
            acao=acao,
            objeto_repr=(objeto or "")[:255],
            ip=_ip(request),
        )
    except Exception:  # auditoria é best-effort
        logger.exception("Falha ao registrar auditoria (acao=%s).", acao)


def _dentro_de(caminho: Path, base: Path) -> bool:
    """Confirma que ``caminho`` (já resolvido) está dentro de ``base`` (resolvido)."""
    try:
        return caminho == base or caminho.is_relative_to(base)
    except ValueError:
        return False


def _resolver_dentro_do_diretorio(backup: Backup) -> Path | None:
    """Resolve o caminho do arquivo do backup e valida que fica em BACKUPS_DIR.

    Retorna o ``Path`` resolvido de um arquivo existente e contido em
    ``BACKUPS_DIR`` ou ``None`` (nome vazio, fora do diretório ou inexistente).
    """
    if not backup.arquivo:
        return None
    try:
        base = Path(settings.BACKUPS_DIR).resolve()
        alvo = backup.caminho_absoluto().resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if not _dentro_de(alvo, base) or not alvo.is_file():
        return None
    return alvo


class BackupListView(AdminRequeridoMixin, ListView):
    """Lista paginada dos backups gerados, do mais recente ao mais antigo."""

    model = Backup
    template_name = "backup/lista.html"
    context_object_name = "backups"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Backup]:
        return Backup.objects.select_related("criado_por").all()


@admin_requerido
@csrf_protect
@require_http_methods(["GET", "POST"])
def novo(request: HttpRequest) -> HttpResponse:
    """Cria um backup: escolhe tipo/escopo/mídia e executa o serviço síncrono."""
    if request.method == "POST":
        form = BackupForm(request.POST)
        if form.is_valid():
            tipo = form.cleaned_data["tipo"]
            try:
                if tipo == Backup.Tipo.MODULO:
                    escopo = form.cleaned_data["escopo"]
                    backup = backup_service.backup_modulo(escopo, criado_por=request.user)
                    _auditar(request, "backup:modulo_gerado", objeto=f"{backup.rotulo} ({escopo})")
                elif tipo == Backup.Tipo.EASYPANEL:
                    # Migração: sempre inclui a mídia (uploads viajam com o pacote).
                    backup = backup_service.backup_easypanel(
                        incluir_media=True, criado_por=request.user
                    )
                    _auditar(request, "backup:easypanel_gerado", objeto=backup.rotulo)
                else:
                    incluir_media = form.cleaned_data.get("incluir_media", False)
                    backup = backup_service.backup_completo(
                        incluir_media=incluir_media, criado_por=request.user
                    )
                    _auditar(request, "backup:completo_gerado", objeto=backup.rotulo)

                if backup.status == Backup.Status.CONCLUIDO:
                    messages.success(
                        request,
                        _("Backup gerado: %(rotulo)s (%(tamanho)s).")
                        % {"rotulo": backup.rotulo, "tamanho": backup.tamanho_texto()},
                        fail_silently=True,
                    )
                else:
                    messages.error(
                        request,
                        _("O backup terminou com erro. %(msg)s") % {"msg": backup.mensagem},
                        fail_silently=True,
                    )
            except ValueError:
                # app_label fora da allowlist (defesa extra além do form).
                messages.error(request, _("Módulo inválido para backup."), fail_silently=True)
            except Exception:
                logger.exception("Falha inesperada ao gerar o backup.")
                messages.error(
                    request, _("Não foi possível gerar o backup. Tente novamente."), fail_silently=True
                )
            return redirect("backup:lista")
    else:
        form = BackupForm()

    contexto = {
        "form": form,
        "modulos": backup_service.modulos_disponiveis(),
    }
    return render(request, "backup/novo.html", contexto)


@admin_requerido
@require_http_methods(["GET"])
def baixar(request: HttpRequest, pk: int) -> HttpResponse:
    """Baixa o arquivo do backup com validação anti path traversal."""
    backup = get_object_or_404(Backup, pk=pk)
    alvo = _resolver_dentro_do_diretorio(backup)
    if alvo is None:
        raise Http404(_("Arquivo de backup não encontrado."))

    _auditar(request, "backup:baixado", objeto=backup.arquivo)
    # ``filename`` sempre a partir do nome interno (gerado pelo sistema, sem path).
    nome_seguro = Path(backup.arquivo).name
    return FileResponse(open(alvo, "rb"), as_attachment=True, filename=nome_seguro)


@admin_requerido
@csrf_protect
@require_POST
def excluir(request: HttpRequest, pk: int) -> HttpResponse:
    """Apaga o arquivo (só se dentro de ``BACKUPS_DIR``) e o registro do backup."""
    backup = get_object_or_404(Backup, pk=pk)
    rotulo = backup.rotulo or backup.escopo
    arquivo = backup.arquivo

    alvo = _resolver_dentro_do_diretorio(backup)
    if alvo is not None:
        try:
            alvo.unlink()
        except OSError:
            logger.exception("Falha ao remover o arquivo do backup %s.", backup.pk)

    backup.delete()
    _auditar(request, "backup:excluido", objeto=f"{rotulo} ({arquivo})")
    messages.success(request, _("Backup removido."), fail_silently=True)
    return redirect("backup:lista")

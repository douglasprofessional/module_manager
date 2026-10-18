"""Serviço de geração de backups (adendo 2 — MÓDULO 4). SEGURANÇA CRÍTICA.

Regras de segurança aplicadas aqui:

- A saída fica SEMPRE dentro de ``settings.BACKUPS_DIR`` (criado com
  ``mkdir(parents=True, exist_ok=True)``). Os nomes de arquivo são gerados pelo
  sistema (timestamp + uuid curto), NUNCA a partir de entrada do usuário.
- ``modulos_disponiveis()`` é a ALLOWLIST: só apps registrados no núcleo
  (``registro.todos()``, com ``slug == app_label``) mais os apps de núcleo
  (``contas``, ``nucleo``) podem ser exportados. ``backup_modulo`` valida o
  ``app_label`` contra essa lista antes de qualquer coisa.
- ``pg_dump`` (Postgres) roda via ``subprocess`` na FORMA-LISTA (nunca
  ``shell=True``); a senha vai por ``env['PGPASSWORD']`` — jamais interpolada no
  comando. Se o binário não existir, registra um aviso e segue só com o fixture.
- Nenhum segredo é registrado em log nem colocado nas mensagens do ``Backup``
  (não incluímos ``stderr`` do ``pg_dump``, que poderia vazar dados de conexão).
- Cada etapa do backup completo é tolerante a falhas: uma etapa que falha vira
  um aviso na mensagem, sem abortar as demais.
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.backup.models import Backup
from apps.nucleo.modulos import registro

logger = logging.getLogger("modulos.backup.services")

# Apps de núcleo sempre disponíveis para backup (fora do registro de módulos).
APPS_NUCLEO: list[tuple[str, str]] = [
    ("contas", "Núcleo (contas/usuários e auditoria)"),
    ("nucleo", "Núcleo (contas/usuários e auditoria)"),
]

# No backup completo excluímos estes apps para uma restauração limpa (loaddata).
EXCLUIR_COMPLETO: list[str] = ["contenttypes", "auth.permission"]

# Teto de tempo para o pg_dump (segundos) — evita processo pendurado.
TIMEOUT_PGDUMP = 1800

# Tamanho do bloco de leitura ao calcular checksums (64 KiB).
_BLOCO = 64 * 1024


# ---------------------------------------------------------------------------
# Auxiliares internos
# ---------------------------------------------------------------------------
def _diretorio_saida() -> Path:
    """Retorna o diretório de backups garantindo que ele exista."""
    diretorio = Path(settings.BACKUPS_DIR)
    diretorio.mkdir(parents=True, exist_ok=True)
    return diretorio


def _carimbo() -> str:
    """Carimbo de tempo seguro para nomes de arquivo (sem espaços/':')."""
    momento = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    return f"{momento}_{uuid.uuid4().hex[:6]}"


def _checksum_sha256(caminho: Path) -> str:
    """Calcula o SHA-256 do arquivo em blocos (não carrega tudo em memória)."""
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(_BLOCO), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _remover_silencioso(caminho: Path) -> None:
    """Remove um arquivo temporário/parcial ignorando erros."""
    try:
        caminho.unlink(missing_ok=True)
    except OSError:
        logger.debug("Não foi possível remover o arquivo temporário %s.", caminho.name)


# ---------------------------------------------------------------------------
# Allowlist de módulos
# ---------------------------------------------------------------------------
def modulos_disponiveis() -> list[tuple[str, str]]:
    """Retorna a ALLOWLIST de apps exportáveis: ``[(app_label, rótulo), ...]``.

    Composta pelos módulos registrados no núcleo (``slug == app_label``) mais os
    apps de núcleo (``contas``, ``nucleo``). Nenhuma outra app pode ser
    exportada. Só entram apps realmente instalados (checados no registro de apps
    do Django), como defesa adicional.
    """
    from django.apps import apps as django_apps

    disponiveis: list[tuple[str, str]] = []
    vistos: set[str] = set()

    try:
        modulos = registro.todos()
    except Exception:  # pragma: no cover - proteção defensiva
        logger.exception("Falha ao listar módulos registrados para backup.")
        modulos = []

    for modulo in modulos:
        slug = (getattr(modulo, "slug", "") or "").strip()
        if not slug or slug in vistos:
            continue
        if slug not in django_apps.app_configs:
            continue  # só apps de fato instalados
        vistos.add(slug)
        disponiveis.append((slug, getattr(modulo, "nome", "") or slug))

    for app_label, rotulo in APPS_NUCLEO:
        if app_label in vistos or app_label not in django_apps.app_configs:
            continue
        vistos.add(app_label)
        disponiveis.append((app_label, rotulo))

    return disponiveis


def _rotulo_do_app(app_label: str) -> str | None:
    """Rótulo amigável do app se ele estiver na allowlist; senão ``None``."""
    return dict(modulos_disponiveis()).get(app_label)


# ---------------------------------------------------------------------------
# Backup por módulo (fixture .json.gz)
# ---------------------------------------------------------------------------
def backup_modulo(app_label: str, criado_por=None) -> Backup:
    """Gera um backup dos dados de UM módulo como fixture Django (``.json.gz``).

    Valida ``app_label`` contra a allowlist (levanta ``ValueError`` se estiver
    fora). O arquivo é um ``dumpdata`` com chaves naturais, restaurável com
    ``manage.py loaddata``.
    """
    rotulo = _rotulo_do_app(app_label)
    if rotulo is None:
        raise ValueError(f"App '{app_label}' fora da allowlist de backup.")

    diretorio = _diretorio_saida()
    nome_arquivo = f"modulo_{app_label}_{_carimbo()}.json.gz"
    caminho = diretorio / nome_arquivo

    backup = Backup.objects.create(
        tipo=Backup.Tipo.MODULO,
        escopo=app_label,
        rotulo=rotulo,
        arquivo=nome_arquivo,
        incluir_media=False,
        status=Backup.Status.EXECUTANDO,
        criado_por=criado_por,
    )

    try:
        with gzip.open(caminho, "wt", encoding="utf-8") as saida:
            call_command(
                "dumpdata",
                app_label,
                format="json",
                indent=2,
                use_natural_foreign_keys=True,
                use_natural_primary_keys=True,
                stdout=saida,
            )
        backup.tamanho_bytes = caminho.stat().st_size
        backup.checksum_sha256 = _checksum_sha256(caminho)
        backup.status = Backup.Status.CONCLUIDO
        backup.concluido_em = timezone.now()
        backup.mensagem = (
            f"Fixture do módulo '{rotulo}' ({app_label}) gerada. "
            "Restaure com: manage.py loaddata <arquivo> (após descompactar o .gz)."
        )
        backup.save()
        logger.info("Backup de módulo concluído: %s (%s).", app_label, nome_arquivo)
    except Exception as exc:  # tolerante: registra ERRO e limpa o parcial
        logger.exception("Falha ao gerar backup do módulo %s.", app_label)
        _remover_silencioso(caminho)
        backup.status = Backup.Status.ERRO
        backup.tamanho_bytes = 0
        backup.mensagem = f"Erro ao gerar o backup do módulo: {exc.__class__.__name__}."
        backup.save()

    return backup


# ---------------------------------------------------------------------------
# Backup completo (.zip: fixture + banco nativo + mídia opcional)
# ---------------------------------------------------------------------------
def backup_completo(incluir_media: bool = False, criado_por=None) -> Backup:
    """Gera um backup completo em ``.zip``.

    Conteúdo:
      - ``dados/dados_completos.json.gz``: ``dumpdata`` de todos os apps
        (excluindo ``contenttypes`` e ``auth.permission``);
      - ``banco/<dump>``: dump nativo do banco quando possível (sqlite via
        ``.backup()``; postgres via ``pg_dump`` forma-lista);
      - ``media/``: árvore de ``MEDIA_ROOT`` se ``incluir_media`` e ela existir.

    Cada etapa é tolerante a falhas: uma etapa que falha vira aviso na mensagem.
    """
    diretorio = _diretorio_saida()
    nome_arquivo = f"completo_{_carimbo()}.zip"
    caminho = diretorio / nome_arquivo
    rotulo = "Estrutura completa"

    backup = Backup.objects.create(
        tipo=Backup.Tipo.COMPLETO,
        escopo="completo",
        rotulo=rotulo,
        arquivo=nome_arquivo,
        incluir_media=incluir_media,
        status=Backup.Status.EXECUTANDO,
        criado_por=criado_por,
    )

    incluidos: list[str] = []
    avisos: list[str] = []

    try:
        with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as zip_saida:
            _incluir_dados(zip_saida, diretorio, incluidos, avisos)
            _incluir_banco(zip_saida, diretorio, incluidos, avisos)
            if incluir_media:
                _incluir_media(zip_saida, incluidos, avisos)

        backup.tamanho_bytes = caminho.stat().st_size
        backup.checksum_sha256 = _checksum_sha256(caminho)
        backup.status = Backup.Status.CONCLUIDO
        backup.concluido_em = timezone.now()
        backup.mensagem = _montar_mensagem(incluidos, avisos)
        backup.save()
        logger.info("Backup completo concluído: %s.", nome_arquivo)
    except Exception as exc:  # falha do próprio zip: registra ERRO e limpa
        logger.exception("Falha ao gerar o backup completo.")
        _remover_silencioso(caminho)
        backup.status = Backup.Status.ERRO
        backup.tamanho_bytes = 0
        backup.mensagem = f"Erro ao gerar o backup completo: {exc.__class__.__name__}."
        backup.save()

    return backup


def _montar_mensagem(incluidos: list[str], avisos: list[str]) -> str:
    """Compõe a mensagem final do backup completo (incluídos + avisos)."""
    partes: list[str] = []
    if incluidos:
        partes.append("Incluídos: " + ", ".join(incluidos) + ".")
    if avisos:
        partes.append("Avisos: " + " ".join(avisos))
    return " ".join(partes) or "Backup completo gerado."


def _incluir_dados(zip_saida: zipfile.ZipFile, diretorio: Path, incluidos: list[str], avisos: list[str]) -> None:
    """Adiciona ``dados/dados_completos.json.gz`` (fixture de todos os apps)."""
    temporario = diretorio / f".tmp_dados_{uuid.uuid4().hex}.json.gz"
    try:
        with gzip.open(temporario, "wt", encoding="utf-8") as saida:
            call_command(
                "dumpdata",
                format="json",
                indent=2,
                use_natural_foreign_keys=True,
                use_natural_primary_keys=True,
                exclude=EXCLUIR_COMPLETO,
                stdout=saida,
            )
        zip_saida.write(temporario, arcname="dados/dados_completos.json.gz")
        incluidos.append("dados (fixture de todos os apps)")
    except Exception:
        logger.exception("Falha ao exportar os dados completos (dumpdata).")
        avisos.append("dados completos não puderam ser exportados.")
    finally:
        _remover_silencioso(temporario)


def _incluir_banco(zip_saida: zipfile.ZipFile, diretorio: Path, incluidos: list[str], avisos: list[str]) -> None:
    """Adiciona o dump nativo do banco sob ``banco/`` quando possível."""
    config = settings.DATABASES.get("default", {})
    engine = (config.get("ENGINE") or "").lower()

    if "sqlite" in engine:
        _incluir_banco_sqlite(zip_saida, diretorio, config, incluidos, avisos)
    elif "postgresql" in engine or "postgis" in engine:
        _incluir_banco_postgres(zip_saida, diretorio, config, incluidos, avisos)
    else:
        avisos.append(
            f"banco '{engine or 'desconhecido'}' sem dump nativo suportado; "
            "incluído apenas o fixture de dados."
        )


def _incluir_banco_sqlite(zip_saida, diretorio, config, incluidos, avisos) -> None:
    """Copia o banco sqlite de forma consistente via ``Connection.backup()``."""
    origem = config.get("NAME")
    if not origem or not Path(origem).exists():
        avisos.append("banco sqlite não encontrado em disco; não incluído.")
        return

    temporario = diretorio / f".tmp_db_{uuid.uuid4().hex}.sqlite3"
    try:
        conexao_origem = sqlite3.connect(str(origem))
        try:
            conexao_destino = sqlite3.connect(str(temporario))
            try:
                conexao_origem.backup(conexao_destino)
            finally:
                conexao_destino.close()
        finally:
            conexao_origem.close()
        zip_saida.write(temporario, arcname="banco/db.sqlite3")
        incluidos.append("banco (sqlite)")
    except Exception:
        logger.exception("Falha ao copiar o banco sqlite para o backup.")
        avisos.append("banco sqlite não pôde ser copiado.")
    finally:
        _remover_silencioso(temporario)


def _incluir_banco_postgres(zip_saida, diretorio, config, incluidos, avisos) -> None:
    """Executa ``pg_dump`` na forma-lista (sem shell) e adiciona o dump ao zip.

    A senha vai por ``PGPASSWORD`` no ambiente do processo — nunca no comando.
    Se ``pg_dump`` não existir, apenas registra aviso e segue.
    """
    binario = shutil.which("pg_dump")
    if not binario:
        avisos.append("pg_dump não encontrado no PATH; banco não incluído (só o fixture de dados).")
        return

    nome = config.get("NAME") or ""
    usuario = config.get("USER") or ""
    host = config.get("HOST") or "localhost"
    porta = str(config.get("PORT") or "5432")
    senha = config.get("PASSWORD") or ""

    if not nome:
        avisos.append("nome do banco Postgres ausente na configuração; banco não incluído.")
        return

    temporario = diretorio / f".tmp_db_{uuid.uuid4().hex}.dump"
    comando = [binario, "-Fc", "-h", host, "-p", porta]
    if usuario:
        comando += ["-U", usuario]
    comando += ["-w", "-f", str(temporario), nome]  # -w: nunca pedir senha interativa

    ambiente = os.environ.copy()
    if senha:
        ambiente["PGPASSWORD"] = senha  # segredo só no env, jamais no comando/log

    try:
        # NUNCA shell=True. capture_output evita poluir stdout/stderr do processo;
        # o conteúdo capturado NÃO é logado nem exposto (pode conter dados sensíveis).
        subprocess.run(
            comando,
            env=ambiente,
            check=True,
            capture_output=True,
            timeout=TIMEOUT_PGDUMP,
        )
        zip_saida.write(temporario, arcname="banco/postgres.dump")
        incluidos.append("banco (postgres/pg_dump)")
    except FileNotFoundError:
        avisos.append("pg_dump não encontrado; banco não incluído.")
    except subprocess.TimeoutExpired:
        logger.warning("pg_dump excedeu o tempo limite (%ss).", TIMEOUT_PGDUMP)
        avisos.append("pg_dump excedeu o tempo limite; banco não incluído.")
    except subprocess.CalledProcessError as exc:
        # Não incluir exc.stderr na mensagem: pode conter detalhes de conexão.
        logger.warning("pg_dump falhou (código %s).", exc.returncode)
        avisos.append("pg_dump falhou ao exportar o banco; incluído apenas o fixture de dados.")
    finally:
        _remover_silencioso(temporario)


# ---------------------------------------------------------------------------
# Export de MIGRAÇÃO para EasyPanel (.zip: banco + mídia + fixture + manifesto)
# ---------------------------------------------------------------------------
def backup_easypanel(incluir_media: bool = True, criado_por=None) -> Backup:
    """Gera um pacote de MIGRAÇÃO pronto para transferir a plataforma a outro
    servidor EasyPanel.

    Conteúdo do ``.zip``:
      - ``banco/<dump>``: dump nativo do banco (pg_dump -Fc / sqlite) — a via
        recomendada de restauração;
      - ``dados/dados_completos.json.gz``: fixture (fallback multi-banco);
      - ``media/``: uploads (logo, fotos, imagens) — por padrão incluídos;
      - ``MIGRACAO-EASYPANEL.md``: passo a passo de restauração no EasyPanel;
      - ``.env.exemplo``: variáveis de ambiente necessárias (com AVISO sobre
        preservar ``modulos_FERNET_KEY`` e ``SECRET_KEY``);
      - ``manifesto.json``: metadados (data, engine, versões).
    """
    diretorio = _diretorio_saida()
    nome_arquivo = f"easypanel_{_carimbo()}.zip"
    caminho = diretorio / nome_arquivo
    rotulo = "Migração EasyPanel"

    backup = Backup.objects.create(
        tipo=Backup.Tipo.EASYPANEL,
        escopo="easypanel",
        rotulo=rotulo,
        arquivo=nome_arquivo,
        incluir_media=incluir_media,
        status=Backup.Status.EXECUTANDO,
        criado_por=criado_por,
    )

    incluidos: list[str] = []
    avisos: list[str] = []

    try:
        with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as zip_saida:
            _incluir_banco(zip_saida, diretorio, incluidos, avisos)
            _incluir_dados(zip_saida, diretorio, incluidos, avisos)
            if incluir_media:
                _incluir_media(zip_saida, incluidos, avisos)
            # Manifesto + instruções + .env de exemplo (texto — sem segredos reais).
            zip_saida.writestr("MIGRACAO-EASYPANEL.md", _instrucoes_easypanel())
            zip_saida.writestr(".env.exemplo", _env_exemplo_easypanel())
            zip_saida.writestr("manifesto.json", _manifesto_easypanel(incluidos))
            incluidos.append("manifesto + instruções + .env.exemplo")

        backup.tamanho_bytes = caminho.stat().st_size
        backup.checksum_sha256 = _checksum_sha256(caminho)
        backup.status = Backup.Status.CONCLUIDO
        backup.concluido_em = timezone.now()
        backup.mensagem = _montar_mensagem(incluidos, avisos)
        backup.save()
        logger.info("Export EasyPanel concluído: %s.", nome_arquivo)
    except Exception as exc:
        logger.exception("Falha ao gerar o export EasyPanel.")
        _remover_silencioso(caminho)
        backup.status = Backup.Status.ERRO
        backup.tamanho_bytes = 0
        backup.mensagem = f"Erro ao gerar o export EasyPanel: {exc.__class__.__name__}."
        backup.save()

    return backup


def _manifesto_easypanel(incluidos: list[str]) -> str:
    """Metadados do pacote (JSON legível). Sem segredos."""
    import json

    config = settings.DATABASES.get("default", {})
    dados = {
        "tipo": "migracao-easypanel",
        "gerado_em": timezone.localtime().isoformat(),
        "engine_banco": (config.get("ENGINE") or "").split(".")[-1],
        "conteudo": incluidos,
        "observacao": (
            "Preserve modulos_FERNET_KEY e SECRET_KEY do servidor de ORIGEM no "
            "destino, senão segredos cifrados (ex.: senha SMTP) e sessões quebram."
        ),
    }
    return json.dumps(dados, ensure_ascii=False, indent=2)


def _env_exemplo_easypanel() -> str:
    """Modelo de variáveis de ambiente para o app no EasyPanel de destino."""
    return (
        "# Variáveis de ambiente para restaurar a plataforma no EasyPanel.\n"
        "# Preencha os valores no painel do EasyPanel (aba Environment do serviço web).\n"
        "# ATENÇÃO: use as MESMAS chaves do servidor de origem nos dois itens abaixo,\n"
        "# senão segredos cifrados (senha SMTP) e sessões deixam de funcionar.\n"
        "SECRET_KEY=coloque-a-mesma-do-servidor-de-origem\n"
        "modulos_FERNET_KEY=coloque-a-mesma-do-servidor-de-origem\n"
        "\n"
        "DEBUG=False\n"
        "ALLOWED_HOSTS=seu-dominio.com.br,www.seu-dominio.com.br\n"
        "CSRF_TRUSTED_ORIGINS=https://seu-dominio.com.br\n"
        "SITE_URL=https://seu-dominio.com.br\n"
        "DJANGO_ADMIN_URL=painel-interno-troque-isto/\n"
        "\n"
        "# Banco de dados (serviço Postgres do EasyPanel):\n"
        "DATABASE_URL=postgres://USUARIO:SENHA@HOST:5432/NOME_DO_BANCO\n"
        "\n"
        "# Cache/sessão compartilhados (serviço Redis do EasyPanel):\n"
        "CACHE_BACKEND=redis\n"
        "REDIS_URL=redis://HOST:6379/1\n"
        "\n"
        "# Superusuário inicial (opcional — só no primeiro boot):\n"
        "DJANGO_SUPERUSER_EMAIL=admin@seu-dominio.com.br\n"
        "DJANGO_SUPERUSER_PASSWORD=defina-uma-senha-forte\n"
        "DJANGO_SUPERUSER_NOME_COMPLETO=Administrador\n"
    )


def _instrucoes_easypanel() -> str:
    """Passo a passo (PT-BR) de restauração no EasyPanel de destino."""
    return (
        "# Migração da plataforma para outro servidor EasyPanel\n\n"
        "Este pacote contém tudo para recriar a plataforma em um novo servidor "
        "EasyPanel.\n\n"
        "## Conteúdo\n"
        "- `banco/` — dump nativo do banco (via recomendada de restauração).\n"
        "- `dados/dados_completos.json.gz` — fixture de todos os apps (fallback).\n"
        "- `media/` — uploads (logo do sistema, fotos de perfil, imagens).\n"
        "- `.env.exemplo` — variáveis de ambiente a definir no destino.\n"
        "- `manifesto.json` — metadados do pacote.\n\n"
        "## Passos no servidor EasyPanel de destino\n"
        "1. Crie um novo projeto/serviço a partir do repositório GitHub (branch "
        "`main`) — o mesmo Dockerfile é usado no build.\n"
        "2. Crie os serviços **Postgres** e **Redis** no projeto.\n"
        "3. Na aba *Environment* do serviço web, defina as variáveis do "
        "`.env.exemplo`. **Use a MESMA `modulos_FERNET_KEY` e `SECRET_KEY` da "
        "origem** (senão a senha SMTP cifrada e as sessões quebram).\n"
        "4. Faça o deploy (o entrypoint roda migrações e cria a tabela de cache).\n"
        "5. Restaure o banco:\n"
        "   - **Postgres**: envie `banco/postgres.dump` ao container e rode "
        "`pg_restore --clean --if-exists -d \"$DATABASE_URL\" banco/postgres.dump`.\n"
        "   - **Alternativa (qualquer banco)**: descompacte "
        "`dados/dados_completos.json.gz` e rode "
        "`python manage.py loaddata dados_completos.json`.\n"
        "6. Restaure a mídia: copie o conteúdo de `media/` para o volume de "
        "mídia do serviço (`/app/media`).\n"
        "7. Rode `python manage.py collectstatic --noinput` (o entrypoint já faz).\n"
        "8. Acesse o domínio e confira o login e o dashboard.\n\n"
        "> Dica: para restauração via fixture, garanta que as migrações já foram "
        "aplicadas antes do `loaddata`.\n"
    )


def _incluir_media(zip_saida: zipfile.ZipFile, incluidos: list[str], avisos: list[str]) -> None:
    """Adiciona a árvore de ``MEDIA_ROOT`` sob ``media/`` se ela existir."""
    media_root_bruto = getattr(settings, "MEDIA_ROOT", "")
    if not media_root_bruto:
        avisos.append("MEDIA_ROOT não configurado; mídia não incluída.")
        return

    media_root = Path(media_root_bruto)
    if not media_root.is_dir():
        avisos.append("MEDIA_ROOT inexistente; mídia não incluída.")
        return

    total = 0
    try:
        for arquivo in media_root.rglob("*"):
            if arquivo.is_file():
                relativo = arquivo.relative_to(media_root)
                zip_saida.write(arquivo, arcname=str(Path("media") / relativo))
                total += 1
        if total:
            incluidos.append(f"mídia ({total} arquivo(s) de MEDIA_ROOT)")
        else:
            avisos.append("MEDIA_ROOT vazio; nenhuma mídia incluída.")
    except Exception:
        logger.exception("Falha ao incluir a mídia no backup completo.")
        avisos.append("mídia não pôde ser incluída por completo.")

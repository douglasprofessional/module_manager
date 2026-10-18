"""Coleta segura de métricas de um servidor via SSH (adendo 2 — MÓDULO 3).

SEGURANÇA CRÍTICA (seção 9 da SPEC + checklist do adendo):

- ``import paramiko`` é LAZY (dentro da função). Se ausente, retorna métrica com
  ``erro="paramiko não instalado"`` — não derruba o boot nem a view.
- Verificação de host key com TOFU (Trust On First Use), feita ANTES da
  autenticação por uma ``MissingHostKeyPolicy`` customizada. O paramiko chama a
  política logo após a troca de chaves e ANTES de enviar credenciais — assim, se
  a host key mudou, a conexão é abortada sem jamais vazar a senha/chave para um
  possível atacante (MITM):
  * host_key_fingerprint vazio  -> aprende o fingerprint (retorna ``fingerprint_novo``
    para a view persistir);
  * preenchido e DIFERENTE       -> aborta ANTES da auth e RECUSA a coleta (MITM);
  * preenchido e igual           -> segue para a autenticação.
  Não persistimos ``known_hosts``: a decisão de confiança é NOSSA e explícita.
- Executa UM comando FIXO e read-only. O texto do comando NUNCA contém dados do
  servidor/usuário. Host, porta e usuário vão como PARÂMETROS de
  ``paramiko.connect`` (jamais interpolados em shell).
- Timeouts de conexão e de execução; a conexão é sempre fechada no ``finally``.
- NENHUM segredo aparece em log ou em mensagem de exceção (mensagens genéricas).

Retorno: ``dict`` com todas as chaves de ``LeituraMetrica`` + ``"online"`` +
``"erro"`` + ``"fingerprint_novo"`` (ou ``None``).
"""
from __future__ import annotations

import base64
import hashlib
import logging

logger = logging.getLogger("modulos.monitoramento.ssh_coletor")

# Timeouts (segundos). O comando dorme 1s para amostrar a CPU, por isso a
# execução tem folga maior que a conexão.
TIMEOUT_CONEXAO = 10
TIMEOUT_COMANDO = 20

# Comando FIXO, read-only. Marcadores delimitam cada bloco para o parse.
# NUNCA interpolar host/usuário/dados aqui — este texto é 100% constante.
COMANDO_COLETA = (
    "echo MON_STAT1_INI; grep '^cpu ' /proc/stat; echo MON_STAT1_FIM\n"
    "sleep 1\n"
    "echo MON_STAT2_INI; grep '^cpu ' /proc/stat; echo MON_STAT2_FIM\n"
    "echo MON_MEM_INI; cat /proc/meminfo; echo MON_MEM_FIM\n"
    "echo MON_DISK_INI; df -kP /; echo MON_DISK_FIM\n"
    "echo MON_UP_INI; cat /proc/uptime; echo MON_UP_FIM\n"
    "echo MON_LOAD_INI; cat /proc/loadavg; echo MON_LOAD_FIM\n"
    "echo MON_NPROC_INI; nproc; echo MON_NPROC_FIM\n"
    "echo MON_UNAME_INI; uname -sr; echo MON_UNAME_FIM\n"
)


class _HostKeyAlterada(Exception):
    """A host key mudou em relação ao fingerprint conhecido (possível MITM).

    Levantada DENTRO da política de host key (antes da autenticação) para
    abortar a conexão sem enviar credenciais ao servidor não confiável.
    """


def _metrica_base(erro: str = "", online: bool = False, fingerprint_novo=None) -> dict:
    """Retorna um dict de métricas com todas as chaves (valores nulos)."""
    return {
        "online": online,
        "cpu_pct": None,
        "mem_pct": None,
        "mem_total_mb": None,
        "mem_usada_mb": None,
        "disco_pct": None,
        "disco_total_gb": None,
        "disco_usado_gb": None,
        "uptime_segundos": None,
        "carga1": None,
        "carga5": None,
        "carga15": None,
        "nucleos": None,
        "sistema": "",
        "erro": erro,
        "fingerprint_novo": fingerprint_novo,
    }


def coletar_metricas(servidor) -> dict:
    """Coleta as métricas de ``servidor`` via SSH de forma segura.

    Retorna sempre um ``dict`` (nunca lança): em falha, ``online=False`` e
    ``erro`` traz uma mensagem GENÉRICA (sem segredos).
    """
    try:
        import paramiko  # import LAZY: só quando realmente vamos coletar
    except ImportError:
        logger.error("paramiko não está instalado; a coleta SSH está indisponível.")
        return _metrica_base(erro="paramiko não instalado")

    cliente = paramiko.SSHClient()
    # Verificação de host key ANTES da autenticação: a política customizada
    # compara o fingerprint (TOFU) e aborta em caso de mudança, sem enviar
    # credenciais. Não persistimos known_hosts.
    politica = _criar_politica(paramiko, servidor.host_key_fingerprint)
    cliente.set_missing_host_key_policy(politica)

    try:
        parametros = {
            "hostname": servidor.host,
            "port": servidor.porta_ssh,
            "username": servidor.usuario,
            "timeout": TIMEOUT_CONEXAO,
            "banner_timeout": TIMEOUT_CONEXAO,
            "auth_timeout": TIMEOUT_CONEXAO,
            "allow_agent": False,
            "look_for_keys": False,
        }

        # Credenciais decifradas apenas em memória, nunca logadas.
        if servidor.metodo_auth == servidor.MetodoAuth.CHAVE:
            parametros["pkey"] = _carregar_chave_privada(
                paramiko, servidor.chave_privada, servidor.passphrase
            )
        else:
            parametros["password"] = servidor.senha

        # A política roda durante o connect (pós-KEX / pré-auth). Se a host key
        # mudou, ``_HostKeyAlterada`` é levantada aqui e a auth NÃO acontece.
        cliente.connect(**parametros)

        # TOFU: se aprendeu um fingerprint novo (campo estava vazio), a view persiste.
        fingerprint_novo = politica.aprendido

        # ---- Executa o comando FIXO e faz o parse em Python --------------
        _stdin, stdout, _stderr = cliente.exec_command(
            COMANDO_COLETA, timeout=TIMEOUT_COMANDO
        )
        saida = stdout.read().decode("utf-8", errors="replace")

        metricas = _parsear_saida(saida)
        metricas["online"] = True
        metricas["erro"] = ""
        metricas["fingerprint_novo"] = fingerprint_novo
        return metricas

    except _HostKeyAlterada:
        # Host key divergente: coleta recusada (possível MITM). Sem segredos.
        logger.warning(
            "Host key do servidor %s mudou; coleta recusada (possível MITM).",
            getattr(servidor, "pk", "?"),
        )
        return _metrica_base(erro="host key mudou — possível MITM; coleta recusada")
    except Exception as exc:  # noqa: BLE001 - resiliência: nunca vaza segredo
        # Mensagem GENÉRICA por tipo; jamais usa str(exc) (pode conter detalhes).
        logger.warning(
            "Falha ao coletar métricas do servidor %s (%s).",
            getattr(servidor, "pk", "?"),
            type(exc).__name__,
        )
        return _metrica_base(erro=_mensagem_erro(exc))
    finally:
        try:
            cliente.close()
        except Exception:  # pragma: no cover - fechamento best-effort
            pass


# --------------------------------------------------------------------------
# Auxiliares de segurança / carregamento de chave
# --------------------------------------------------------------------------
def _criar_politica(paramiko, fingerprint_conhecido: str):
    """Cria a política de host key (TOFU) que roda ANTES da autenticação.

    Como não carregamos ``known_hosts``, o paramiko considera toda host key
    "desconhecida" e sempre chama ``missing_host_key`` — momento em que decidimos
    confiar (aprender), seguir (fingerprint igual) ou abortar (fingerprint
    diferente = possível MITM), tudo antes de qualquer credencial ser enviada.
    """

    class _PoliticaTOFU(paramiko.MissingHostKeyPolicy):
        def __init__(self) -> None:
            self.conhecido = (fingerprint_conhecido or "").strip()
            self.aprendido = None  # fingerprint aprendido nesta conexão (TOFU)

        def missing_host_key(self, client, hostname, key) -> None:
            atual = _fingerprint_sha256(key)
            if not self.conhecido:
                # 1ª conexão: aprende o fingerprint e aceita (TOFU).
                self.aprendido = atual
                return
            if self.conhecido != atual:
                # Divergência: aborta antes da auth (não vaza credenciais).
                raise _HostKeyAlterada()
            # Igual ao conhecido: segue para a autenticação.
            return

    return _PoliticaTOFU()


def _carregar_chave_privada(paramiko, texto_chave: str, passphrase: str):
    """Carrega a chave privada de uma string, tentando Ed25519/ECDSA/RSA.

    Usa ``io.StringIO`` (a chave nunca toca o disco). A passphrase é usada se
    houver. NÃO loga o conteúdo da chave nem a passphrase.
    """
    import io

    texto = texto_chave or ""
    if not texto.strip():
        raise ValueError("chave privada ausente")

    senha = passphrase or None
    for classe in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return classe.from_private_key(io.StringIO(texto), password=senha)
        except paramiko.SSHException:
            continue  # formato não corresponde a esta classe; tenta a próxima
    raise ValueError("chave privada inválida ou em formato não suportado")


def _fingerprint_sha256(host_key) -> str:
    """Fingerprint SHA-256 (base64 sem padding) da host key — formato OpenSSH."""
    digest = hashlib.sha256(host_key.asbytes()).digest()
    b64 = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{b64}"


def _mensagem_erro(exc: Exception) -> str:
    """Mapa de exceção -> mensagem GENÉRICA e segura (sem detalhes sensíveis)."""
    import socket

    nome = type(exc).__name__
    if nome == "AuthenticationException":
        return "falha de autenticação"
    if isinstance(exc, socket.timeout) or nome in ("timeout", "SSHException"):
        return "tempo de conexão/execução esgotado"
    if nome in ("NoValidConnectionsError", "gaierror", "ConnectionError"):
        return "não foi possível conectar (host/porta)"
    if isinstance(exc, (ValueError,)):
        return "credencial inválida ou não suportada"
    return "falha ao conectar ou coletar"


# --------------------------------------------------------------------------
# Parse tolerante da saída (valores ausentes -> None)
# --------------------------------------------------------------------------
def _extrair_bloco(texto: str, marcador: str) -> str:
    """Extrai o conteúdo entre ``MON_<marcador>_INI`` e ``MON_<marcador>_FIM``."""
    ini = f"MON_{marcador}_INI"
    fim = f"MON_{marcador}_FIM"
    try:
        i = texto.index(ini) + len(ini)
        j = texto.index(fim, i)
        return texto[i:j].strip()
    except ValueError:
        return ""


def _parsear_saida(saida: str) -> dict:
    """Converte a saída bruta do comando em um dict de métricas (tolerante)."""
    metricas = _metrica_base()

    # CPU (%): dois snapshots de /proc/stat.
    metricas["cpu_pct"] = _parsear_cpu(
        _extrair_bloco(saida, "STAT1"), _extrair_bloco(saida, "STAT2")
    )

    # Memória (/proc/meminfo em kB).
    mem = _parsear_memoria(_extrair_bloco(saida, "MEM"))
    metricas.update(mem)

    # Disco (df -kP / em blocos de 1 kB).
    disco = _parsear_disco(_extrair_bloco(saida, "DISK"))
    metricas.update(disco)

    # Uptime (/proc/uptime: "segundos ociosos").
    metricas["uptime_segundos"] = _parsear_uptime(_extrair_bloco(saida, "UP"))

    # Carga (/proc/loadavg: 1m 5m 15m ...).
    carga = _parsear_loadavg(_extrair_bloco(saida, "LOAD"))
    metricas.update(carga)

    # Núcleos (nproc).
    metricas["nucleos"] = _parsear_int(_extrair_bloco(saida, "NPROC"))

    # Sistema (uname -sr).
    metricas["sistema"] = _extrair_bloco(saida, "UNAME")[:200]

    return metricas


def _campos_cpu(linha: str) -> list[int]:
    """Extrai os contadores inteiros de uma linha ``cpu ...`` do /proc/stat."""
    partes = linha.split()
    valores: list[int] = []
    for parte in partes[1:]:  # ignora o rótulo "cpu"
        if parte.isdigit():
            valores.append(int(parte))
    return valores


def _parsear_cpu(bloco1: str, bloco2: str):
    """Calcula o uso de CPU (%) a partir de dois snapshots de /proc/stat."""
    try:
        c1 = _campos_cpu(bloco1)
        c2 = _campos_cpu(bloco2)
        if len(c1) < 4 or len(c2) < 4:
            return None
        total1, total2 = sum(c1), sum(c2)
        # idle = idle + iowait (índices 3 e 4).
        idle1 = c1[3] + (c1[4] if len(c1) > 4 else 0)
        idle2 = c2[3] + (c2[4] if len(c2) > 4 else 0)
        delta_total = total2 - total1
        delta_idle = idle2 - idle1
        if delta_total <= 0:
            return None
        uso = (1.0 - (delta_idle / delta_total)) * 100.0
        return round(max(0.0, min(100.0, uso)), 1)
    except Exception:  # parse tolerante
        return None


def _parsear_memoria(bloco: str) -> dict:
    """Extrai memória total/usada/percentual de /proc/meminfo (kB)."""
    vazio = {"mem_total_mb": None, "mem_usada_mb": None, "mem_pct": None}
    if not bloco:
        return vazio
    try:
        campos: dict[str, int] = {}
        for linha in bloco.splitlines():
            if ":" not in linha:
                continue
            chave, _, resto = linha.partition(":")
            numero = resto.strip().split()
            if numero and numero[0].isdigit():
                campos[chave.strip()] = int(numero[0])  # em kB

        total_kb = campos.get("MemTotal")
        if not total_kb:
            return vazio
        # MemAvailable é o indicador correto de "livre real"; se ausente,
        # aproxima por MemFree + Buffers + Cached.
        disponivel_kb = campos.get("MemAvailable")
        if disponivel_kb is None:
            disponivel_kb = (
                campos.get("MemFree", 0)
                + campos.get("Buffers", 0)
                + campos.get("Cached", 0)
            )
        usada_kb = max(0, total_kb - disponivel_kb)
        return {
            "mem_total_mb": int(round(total_kb / 1024)),
            "mem_usada_mb": int(round(usada_kb / 1024)),
            "mem_pct": round(usada_kb / total_kb * 100.0, 1),
        }
    except Exception:
        return vazio


def _parsear_disco(bloco: str) -> dict:
    """Extrai disco total/usado/percentual da 2ª linha de ``df -kP /`` (kB)."""
    vazio = {"disco_total_gb": None, "disco_usado_gb": None, "disco_pct": None}
    if not bloco:
        return vazio
    try:
        linhas = [l for l in bloco.splitlines() if l.strip()]
        if len(linhas) < 2:
            return vazio
        # Colunas: Filesystem  1024-blocks  Used  Available  Capacity  Mounted
        partes = linhas[1].split()
        if len(partes) < 4:
            return vazio
        total_kb = int(partes[1])
        usado_kb = int(partes[2])
        if total_kb <= 0:
            return vazio
        return {
            "disco_total_gb": round(total_kb / (1024 * 1024), 1),
            "disco_usado_gb": round(usado_kb / (1024 * 1024), 1),
            "disco_pct": round(usado_kb / total_kb * 100.0, 1),
        }
    except Exception:
        return vazio


def _parsear_uptime(bloco: str):
    """Extrai o uptime em segundos (1º número de /proc/uptime)."""
    if not bloco:
        return None
    try:
        return int(float(bloco.split()[0]))
    except (ValueError, IndexError):
        return None


def _parsear_loadavg(bloco: str) -> dict:
    """Extrai as cargas de 1/5/15 min de /proc/loadavg."""
    vazio = {"carga1": None, "carga5": None, "carga15": None}
    if not bloco:
        return vazio
    try:
        partes = bloco.split()
        return {
            "carga1": float(partes[0]),
            "carga5": float(partes[1]),
            "carga15": float(partes[2]),
        }
    except (ValueError, IndexError):
        return vazio


def _parsear_int(bloco: str):
    """Converte um bloco em inteiro (ou None)."""
    if not bloco:
        return None
    try:
        return int(bloco.split()[0])
    except (ValueError, IndexError):
        return None

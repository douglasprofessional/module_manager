"""Fetcher anti-SSRF e verificação de SSL (seção 9 da SPEC).

Todo acesso a sites de terceiros DEVE passar por :func:`requisicao_segura`.
Nunca use ``requests.get`` direto para URLs de empresas.

Defesas implementadas:

- Aceita apenas esquemas ``http``/``https``.
- Resolve o host com ``socket.getaddrinfo`` e RECUSA a requisição se QUALQUER
  IP resolvido for privado, loopback, link-local, reservado, multicast,
  não especificado ou de faixas especiais (CGNAT, TEST-NET, etc.).
- ``allow_redirects=False``: cada salto de redirecionamento é validado
  manualmente (re-resolvendo e re-checando o IP do novo host) antes de ser
  seguido.
- Timeout curto em toda chamada e limite de tamanho da resposta lendo em
  *stream* com corte em ``max_bytes``.
- User-Agent próprio ``modulosBot/1.0``.

Observação sobre *DNS rebinding*: entre a resolução de checagem e a conexão
efetiva do ``requests`` existe uma janela de TOCTOU. A validação por salto
reduz muito a superfície, mas para ambientes de altíssimo risco o ideal é
fixar o IP validado na conexão. Mantemos a abordagem da SPEC (resolver +
recusar + validar cada salto), documentando o resíduo.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger("modulos.prospeccao.seguranca_rede")

USER_AGENT = "modulosBot/1.0"

# Esquemas aceitos para requisições externas.
_ESQUEMAS_PERMITIDOS = frozenset({"http", "https"})

# Faixas extras (IPv4) que ``ipaddress`` nem sempre classifica como privadas mas
# que também não devem ser acessíveis a partir do fetcher.
_FAIXAS_EXTRA_V4 = (
    ipaddress.ip_network("0.0.0.0/8"),          # "este" host / rede
    ipaddress.ip_network("100.64.0.0/10"),      # CGNAT (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("198.18.0.0/15"),      # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("240.0.0.0/4"),        # reservado (classe E)
)


class ErroRequisicaoSegura(Exception):
    """Levantada quando uma requisição viola as regras de segurança de rede."""


@dataclass
class RespostaSegura:
    """Resultado de :func:`requisicao_segura`.

    Atributos:
        url_final: URL efetiva após os redirecionamentos validados.
        status: código HTTP da resposta final.
        html: corpo da resposta como texto (truncado em ``max_bytes``).
        headers: cabeçalhos da resposta final (dict simples).
        tem_ssl: ``True`` se a URL final usa HTTPS.
    """

    url_final: str
    status: int
    html: str
    headers: dict[str, str] = field(default_factory=dict)
    tem_ssl: bool = False


def _ip_perigoso(ip: ipaddress._BaseAddress) -> bool:
    """Retorna ``True`` se o IP não deve ser acessado pelo fetcher."""
    # IPv6 que mapeia um IPv4 (ex.: ::ffff:127.0.0.1) — checa o IPv4 embutido.
    mapeado = getattr(ip, "ipv4_mapped", None)
    if mapeado is not None:
        return _ip_perigoso(mapeado)

    # ``is_global`` já exclui privados, loopback, link-local, reservados,
    # multicast e não especificados. Usamos como rede de segurança principal.
    if not ip.is_global:
        return True

    # Checagens explícitas (redundância defensiva) + faixas especiais IPv4.
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True

    if ip.version == 4:
        for faixa in _FAIXAS_EXTRA_V4:
            if ip in faixa:
                return True
    return False


def _resolver_ips(host: str, porta: int) -> list[ipaddress._BaseAddress]:
    """Resolve ``host`` para todos os IPs (IPv4/IPv6) via ``getaddrinfo``."""
    try:
        infos = socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ErroRequisicaoSegura(f"Falha ao resolver o host '{host}'.") from exc

    ips: list[ipaddress._BaseAddress] = []
    for familia, _tipo, _proto, _canon, sockaddr in infos:
        endereco = sockaddr[0]
        try:
            ips.append(ipaddress.ip_address(endereco))
        except ValueError:
            # Endereço inesperado: trata como perigoso recusando adiante.
            raise ErroRequisicaoSegura(
                f"Endereço resolvido inválido para '{host}'."
            )
    if not ips:
        raise ErroRequisicaoSegura(f"Nenhum IP resolvido para o host '{host}'.")
    return ips


def _garantir_host_seguro(host: str, porta: int) -> None:
    """Resolve o host e recusa se QUALQUER IP for interno/reservado."""
    if not host:
        raise ErroRequisicaoSegura("URL sem host.")

    # Host pode já ser um literal de IP.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if _ip_perigoso(literal):
            raise ErroRequisicaoSegura(
                f"Acesso recusado: IP não roteável/interno ({host})."
            )
        return

    for ip in _resolver_ips(host, porta):
        if _ip_perigoso(ip):
            # Não expõe o IP interno em detalhe além do necessário.
            raise ErroRequisicaoSegura(
                f"Acesso recusado: '{host}' resolve para IP interno/reservado."
            )


def _validar_e_partes(url: str) -> tuple[str, int]:
    """Valida esquema/host da URL e devolve ``(host, porta)`` seguros."""
    partes = urlparse(url)
    esquema = (partes.scheme or "").lower()
    if esquema not in _ESQUEMAS_PERMITIDOS:
        raise ErroRequisicaoSegura(
            f"Esquema não permitido: '{esquema or '(vazio)'}'. Use http/https."
        )
    host = partes.hostname or ""
    porta = partes.port or (443 if esquema == "https" else 80)
    _garantir_host_seguro(host, porta)
    return host, porta


def requisicao_segura(
    url: str,
    metodo: str = "GET",
    timeout: float = 8,
    max_bytes: int = 2_000_000,
    permitir_redirect: bool = True,
    max_redirects: int = 3,
) -> RespostaSegura:
    """Baixa ``url`` com proteção anti-SSRF e limite de tamanho.

    Args:
        url: endereço http/https a acessar.
        metodo: método HTTP (padrão ``GET``).
        timeout: timeout de conexão/leitura em segundos.
        max_bytes: teto de bytes lidos do corpo (o excedente é descartado).
        permitir_redirect: se ``True``, segue redirecionamentos validando cada
            salto; se ``False``, retorna a própria resposta 3xx.
        max_redirects: número máximo de saltos permitidos.

    Returns:
        :class:`RespostaSegura` com a resposta final.

    Raises:
        ErroRequisicaoSegura: em esquema inválido, host interno, excesso de
            redirecionamentos ou falha de rede.
    """
    sessao = requests.Session()
    cabecalhos = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    url_atual = url
    saltos = 0
    try:
        while True:
            _validar_e_partes(url_atual)  # esquema + host seguros (por salto)
            try:
                resp = sessao.request(
                    metodo,
                    url_atual,
                    timeout=timeout,
                    allow_redirects=False,
                    stream=True,
                    headers=cabecalhos,
                )
            except requests.RequestException as exc:
                raise ErroRequisicaoSegura(
                    f"Falha de rede ao acessar a URL: {type(exc).__name__}."
                ) from exc

            eh_redirect = 300 <= resp.status_code < 400 and "location" in {
                k.lower() for k in resp.headers.keys()
            }

            if eh_redirect and permitir_redirect:
                if saltos >= max_redirects:
                    resp.close()
                    raise ErroRequisicaoSegura("Excesso de redirecionamentos.")
                destino = resp.headers.get("Location", "")
                resp.close()
                proximo = urljoin(url_atual, destino)
                logger.debug("Redirecionamento validado: %s -> %s", url_atual, proximo)
                url_atual = proximo
                saltos += 1
                continue

            # Resposta final: lê o corpo com corte em max_bytes.
            corpo = bytearray()
            try:
                for pedaco in resp.iter_content(chunk_size=8192):
                    if not pedaco:
                        continue
                    corpo.extend(pedaco)
                    if len(corpo) >= max_bytes:
                        del corpo[max_bytes:]
                        logger.debug("Corpo truncado em %d bytes.", max_bytes)
                        break
            except requests.RequestException as exc:
                raise ErroRequisicaoSegura(
                    f"Falha ao ler o corpo da resposta: {type(exc).__name__}."
                ) from exc
            finally:
                resp.close()

            codificacao = resp.encoding or "utf-8"
            try:
                html = bytes(corpo).decode(codificacao, errors="replace")
            except (LookupError, TypeError):
                html = bytes(corpo).decode("utf-8", errors="replace")

            return RespostaSegura(
                url_final=url_atual,
                status=resp.status_code,
                html=html,
                headers=dict(resp.headers),
                tem_ssl=url_atual.lower().startswith("https://"),
            )
    finally:
        sessao.close()


def verificar_ssl(dominio: str, timeout: float = 8) -> dict:
    """Tenta estabelecer TLS em ``dominio``:443 e valida o certificado (SNI).

    Aplica a mesma checagem anti-SSRF do fetcher antes de conectar.

    Returns:
        dict com chaves:
            ``tem_ssl`` (bool): a porta 443 respondeu com handshake TLS.
            ``valido`` (bool): o certificado é válido para o host.
            ``emissor`` (str): CN/organização do emissor (ou "").
            ``emitido_para`` (str): CN do assunto (ou "").
            ``expira_em`` (str): data de expiração em ISO (ou "").
            ``erro`` (str | None): descrição do problema, se houver.
    """
    resultado = {
        "tem_ssl": False,
        "valido": False,
        "emissor": "",
        "emitido_para": "",
        "expira_em": "",
        "erro": None,
    }

    # Normaliza: aceita "https://dominio/...", "dominio" ou "dominio:porta".
    host = dominio.strip()
    if "://" in host:
        host = urlparse(host).hostname or ""
    else:
        host = host.split("/", 1)[0].split(":", 1)[0]

    if not host:
        resultado["erro"] = "domínio vazio"
        return resultado

    try:
        _garantir_host_seguro(host, 443)
    except ErroRequisicaoSegura as exc:
        resultado["erro"] = str(exc)
        return resultado

    contexto = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with contexto.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        # Handshake com verificação bem-sucedido: certificado válido.
        resultado["tem_ssl"] = True
        resultado["valido"] = True
        resultado["emitido_para"] = _campo_cert(cert, "subject", "commonName")
        resultado["emissor"] = _campo_cert(cert, "issuer", "organizationName") or _campo_cert(
            cert, "issuer", "commonName"
        )
        resultado["expira_em"] = _expira_iso(cert.get("notAfter", ""))
    except ssl.SSLCertVerificationError as exc:
        # TLS existe, mas o certificado é inválido (expirado/host errado/CA).
        resultado["tem_ssl"] = True
        resultado["valido"] = False
        resultado["erro"] = f"certificado inválido: {exc.verify_message or exc}"
    except (ssl.SSLError, OSError) as exc:
        resultado["erro"] = f"sem TLS: {type(exc).__name__}"
    return resultado


def _campo_cert(cert: dict | None, secao: str, chave: str) -> str:
    """Extrai um campo (ex.: commonName) de subject/issuer do certificado."""
    if not cert:
        return ""
    for grupo in cert.get(secao, ()):  # tupla de tuplas de pares
        for nome, valor in grupo:
            if nome == chave:
                return str(valor)
    return ""


def _expira_iso(not_after: str) -> str:
    """Converte ``notAfter`` (formato OpenSSL) para ISO 8601, se possível."""
    if not not_after:
        return ""
    try:
        dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return not_after

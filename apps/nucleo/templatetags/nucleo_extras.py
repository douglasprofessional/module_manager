"""Filtros e tags de template do núcleo.

Carregue com ``{% load nucleo_extras %}``.

Filtros:
    moeda           — formata número como real brasileiro (``R$ 1.234,56``).
    iniciais        — até 2 letras maiúsculas a partir de um nome (avatar).
    primeira_letra  — a primeira letra maiúscula de um texto.
    ate             — gera um ``range`` para iterar no template.
    get             — acessa um valor de dict por chave (útil para chaves dinâmicas).

Tags:
    pontos_polyline — pontos normalizados para um ``<polyline>``/``<polygon>`` SVG.
    texto           — texto centralizado em ``apps/nucleo/textos.py`` (ex.:
                      ``{% texto "prospeccao.painel.titulo" %}``; aceita parâmetros
                      nomeados e ``as variavel``).
"""
from __future__ import annotations

from django import template

from apps.nucleo.textos import texto as _texto

register = template.Library()


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
@register.filter
def moeda(valor) -> str:
    """Formata ``valor`` como real brasileiro: ``1234.5`` -> ``"R$ 1.234,50"``.

    Não depende de ``locale`` (evita diferenças entre ambientes). Valores
    inválidos degradam para ``"R$ 0,00"``.
    """
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    # Formata com separador de milhar e 2 casas, depois troca para o padrão BR.
    texto = f"{numero:,.2f}"  # ex.: "1,234.50"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


@register.filter
def iniciais(nome) -> str:
    """Retorna até 2 letras maiúsculas para um avatar (ex.: ``"Maria Costa"`` -> ``"MC"``)."""
    texto = (str(nome) if nome is not None else "").strip()
    if not texto:
        return "?"
    partes = [p for p in texto.split() if p]
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@register.filter
def primeira_letra(texto) -> str:
    """Retorna a primeira letra (maiúscula) de ``texto`` ou ``"?"`` se vazio."""
    valor = (str(texto) if texto is not None else "").strip()
    return valor[0].upper() if valor else "?"


@register.filter
def ate(valor, inicio: int = 0):
    """Gera um ``range`` para iterar no template.

    ``{% for i in 8|ate %}`` itera de 0 a 7. ``{{ valor|ate:inicio }}`` começa
    em ``inicio``. Valores inválidos produzem um range vazio.
    """
    try:
        fim = int(valor)
        ini = int(inicio)
    except (TypeError, ValueError):
        return range(0)
    return range(ini, fim)


@register.filter
def get(dicionario, chave):
    """Acessa ``dicionario[chave]`` de forma tolerante (para chaves dinâmicas).

    Funciona com dict e objetos indexáveis; retorna ``""`` quando ausente.
    """
    if dicionario is None:
        return ""
    if hasattr(dicionario, "get"):
        return dicionario.get(chave, "")
    try:
        return dicionario[chave]
    except (KeyError, IndexError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------
@register.simple_tag
def pontos_polyline(
    serie,
    largura: float = 100.0,
    altura: float = 40.0,
    minimo=None,
    maximo=None,
    preencher: bool = False,
) -> str:
    """Converte uma lista de números em pontos para um ``<polyline>`` SVG.

    Assinatura (uso no template do gráfico de linha do dashboard)::

        {% pontos_polyline painel.serie_encontradas largura=320 altura=90 %}
        {% pontos_polyline serie 320 90 minimo=0 maximo=100 preencher=True %}

    Parâmetros:
        serie: lista de inteiros/floats (os valores da série).
        largura: largura da viewBox (eixo X). Padrão 100.
        altura: altura da viewBox (eixo Y). Padrão 40.
        minimo: valor mapeado à base (Y = altura). Padrão: menor da série.
        maximo: valor mapeado ao topo (Y = 0). Padrão: maior da série.
        preencher: se ``True``, acrescenta os cantos da base
            (``largura,altura`` e ``0,altura``) para uso como ``<polygon>``
            de área preenchida.

    Retorna a string ``"x,y x,y ..."`` (números com até 2 casas), com o eixo Y
    invertido (valores maiores ficam mais ALTOS na tela, como esperado em SVG).
    Série vazia retorna ``""``; um único ponto é desenhado como linha
    horizontal no meio vertical.
    """
    try:
        valores = [float(v) for v in (serie or [])]
    except (TypeError, ValueError):
        valores = []

    if not valores:
        return ""

    try:
        largura = float(largura)
        altura = float(altura)
    except (TypeError, ValueError):
        largura, altura = 100.0, 40.0

    vmin = float(minimo) if minimo is not None else min(valores)
    vmax = float(maximo) if maximo is not None else max(valores)
    faixa = vmax - vmin

    n = len(valores)
    pontos: list[str] = []
    for i, valor in enumerate(valores):
        x = (i / (n - 1)) * largura if n > 1 else largura / 2.0
        if faixa <= 0:
            # Série constante (ou 1 ponto): linha na metade da altura.
            y = altura / 2.0
        else:
            proporcao = (valor - vmin) / faixa
            y = altura - proporcao * altura  # inverte o eixo Y
        pontos.append(f"{round(x, 2)},{round(y, 2)}")

    if preencher:
        # Fecha a área contra a base para permitir preenchimento como polígono.
        pontos.append(f"{round(largura, 2)},{round(altura, 2)}")
        pontos.append(f"0,{round(altura, 2)}")

    return " ".join(pontos)


@register.simple_tag(name="texto")
def texto(chave, **parametros) -> str:
    """Exibe o texto da ``chave`` definido em ``apps/nucleo/textos.py``.

    Exemplos::

        {% texto "nucleo.dashboard.titulo" %}
        {% texto "nucleo.dashboard.subtitulo" nome=request.user.nome_completo %}
        {% texto "prospeccao.lista.titulo" as titulo %}

    O resultado passa pelo autoescape do Django (parâmetros vindos de dados do
    usuário ficam seguros). Chave inexistente exibe o próprio caminho.
    """
    return _texto(str(chave), **parametros)

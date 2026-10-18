"""Utilitarios de datas/meses usados pela regra de negocio."""

from __future__ import annotations

import calendar
from datetime import date, datetime

MESES_PT = [
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

MESES_PT_ABREV = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"Valor de data invalido: {value!r}")


def month_start(value) -> date:
    """Primeiro dia do mes da data informada."""
    valor = _as_date(value)
    return date(valor.year, valor.month, 1)


def last_day_of_month(value) -> date:
    """Ultimo dia do mes da data informada."""
    valor = _as_date(value)
    ultimo = calendar.monthrange(valor.year, valor.month)[1]
    return date(valor.year, valor.month, ultimo)


def add_months(value, months: int) -> date:
    """Soma (ou subtrai) meses preservando o primeiro dia do mes."""
    inicio = month_start(value)
    total = inicio.year * 12 + (inicio.month - 1) + months
    ano, mes = divmod(total, 12)
    return date(ano, mes + 1, 1)


def month_label(value) -> str:
    """Rotulo amigavel em portugues. Ex.: 'Agosto/2026'."""
    valor = _as_date(value)
    return f"{MESES_PT[valor.month - 1].capitalize()}/{valor.year}"


def month_name(month: int) -> str:
    """Nome do mes (1-12) em portugues."""
    if 1 <= month <= 12:
        return MESES_PT[month - 1].capitalize()
    return ""


def parse_month(texto: str | None, default: date | None = None) -> date:
    """
    Converte 'AAAA-MM' ou 'AAAA-MM-DD' no primeiro dia do mes.
    Retorna `default` (ou o mes atual) quando o valor for invalido.
    """
    fallback = month_start(default) if default else month_start(date.today())
    if not texto:
        return fallback
    texto = texto.strip()
    for formato in ("%Y-%m", "%Y-%m-%d", "%m/%Y"):
        try:
            return month_start(datetime.strptime(texto, formato))
        except ValueError:
            continue
    return fallback


def month_options(referencia: date, back: int = 12, forward: int = 6) -> list[dict]:
    """Lista de meses para o seletor do painel (do mais recente ao mais antigo)."""
    opcoes = []
    for delta in range(forward, -back - 1, -1):
        mes = add_months(referencia, delta)
        opcoes.append({"value": mes.strftime("%Y-%m"), "label": month_label(mes), "date": mes})
    return opcoes


def due_date_for(referencia: date, day: int = 10) -> date:
    """Vencimento padrao dentro do mes de referencia (dia 10, ajustado ao mes)."""
    inicio = month_start(referencia)
    ultimo = calendar.monthrange(inicio.year, inicio.month)[1]
    return date(inicio.year, inicio.month, min(day, ultimo))

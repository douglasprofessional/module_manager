# modulos — imagem de produção/local (Python 3.12 slim, usuário não-root).
FROM python:3.12-slim AS base

# Ambiente Python previsível.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Dependências de sistema mínimas.
# - curl: healthcheck ; tini: init (PID 1)
# - postgresql-client: fornece o pg_dump usado no "backup completo" com Postgres.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Instala as dependências Python primeiro (melhor cache de camadas).
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

# Copia o código da aplicação.
COPY . .

# Cria usuário sem privilégios e prepara diretórios graváveis.
# Copia o entrypoint e normaliza finais de linha (evita "exec format error"
# quando o repositório é clonado no Windows com CRLF).
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod 0755 /usr/local/bin/entrypoint.sh

RUN addgroup --system app \
    && adduser --system --ingroup app --home /app app \
    && mkdir -p /app/staticfiles /app/media /app/backups \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5     CMD curl -fsS -o /dev/null -H "X-Forwarded-Proto: https" http://localhost:8000/contas/entrar/ || exit 1

# tini garante o encerramento correto de sinais (PID 1).
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]

# Servidor de aplicação padrão.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

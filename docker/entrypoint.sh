#!/usr/bin/env sh
# Entrypoint do modulos: espera o banco, aplica migrações, coleta estáticos,
# garante o superusuário e (opcionalmente) semeia dados de demonstração.
# Todas as etapas são idempotentes — seguro reexecutar a cada boot.
set -e

# SECRET_KEY estável entre os workers do Gunicorn: sem ela, cada worker geraria
# uma chave efêmera diferente e as sessões seriam invalidadas a cada requisição
# (usuário "deslogado" ao navegar). Em produção (DEBUG desligado) é obrigatória.
if [ -z "$SECRET_KEY" ]; then
  case "$(echo "${DEBUG:-0}" | tr "[:upper:]" "[:lower:]")" in
    1|true|t|yes|y|sim|on)
      SECRET_KEY="$(python -c "from django.core.management.utils import get_random_secret_key as g; print(g())")"
      export SECRET_KEY
      echo "!! SECRET_KEY ausente: gerada uma chave temporária (somente DEBUG)."
      ;;
    *)
      echo "!! SECRET_KEY é obrigatória em produção. Abortando."
      exit 1
      ;;
  esac
fi

echo "==> Aguardando o banco de dados..."
tentativas=0
until python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from django.db import connections; connections['default'].ensure_connection()" 2>/dev/null; do
  tentativas=$((tentativas + 1))
  if [ "$tentativas" -ge 30 ]; then
    echo "!! Banco de dados indisponível após várias tentativas. Abortando."
    exit 1
  fi
  echo "   banco indisponível, nova tentativa em 2s... ($tentativas/30)"
  sleep 2
done
echo "==> Banco disponível."

# As migrações são geradas em tempo de execução porque o repositório versiona
# apenas os pacotes 'migrations' vazios (não há Python no ambiente de autoria).
# makemigrations é no-op quando não há mudanças de modelo.
echo "==> Gerando/aplicando migrações..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

echo "==> Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

# Biblioteca de 10 modelos de e-mail (recurso do produto, não é dado de demo).
# Idempotente: não sobrescreve modelos já existentes/editados.
echo "==> Garantindo a biblioteca de modelos de e-mail..."
python manage.py seed_templates_email || echo "   (seed_templates_email ignorado)"

# Cache de banco (throttle de login compartilhado entre workers) — idempotente.
if [ "$CACHE_BACKEND" = "db" ] || [ "$CACHE_BACKEND" = "database" ]; then
  echo "==> Garantindo a tabela de cache (DatabaseCache)..."
  python manage.py createcachetable
fi

# Superusuário idempotente: cria a partir de DJANGO_SUPERUSER_* se ainda não existir.
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "==> Garantindo superusuário ($DJANGO_SUPERUSER_EMAIL)..."
  if python manage.py createsuperuser --noinput >/dev/null 2>&1; then
    echo "   superusuário criado."
  else
    echo "   superusuário já existe (ou criação ignorada)."
  fi
fi

# Dados de demonstração idempotentes (para testar o layout localmente).
# Também habilita todos os módulos (em produção eles começam DESLIGADOS).
if [ "$SEED_DEMO" = "1" ]; then
  echo "==> Semeando dados de demonstração (idempotente)..."
  python manage.py seed_prospeccao || echo "   (seed_prospeccao ignorado)"
  python manage.py seed_kanban || echo "   (seed_kanban ignorado)"
  python manage.py seed_sla || echo "   (seed_sla ignorado)"
  python manage.py seed_monitoramento || echo "   (seed_monitoramento ignorado)"
  python manage.py seed_email_marketing || echo "   (seed_email_marketing ignorado)"
  python manage.py seed_cupons --demo || python manage.py seed_cupons || echo "   (seed_cupons ignorado)"
  python manage.py seed_blog || echo "   (seed_blog ignorado)"
  echo "==> Habilitando módulos para a demonstração..."
  python manage.py habilitar_modulos_demo || echo "   (habilitar_modulos_demo ignorado)"
fi

echo "==> Subindo aplicação: $*"
exec "$@"

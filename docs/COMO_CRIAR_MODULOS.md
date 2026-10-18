# Como criar um novo módulo no modulos

Este é um tutorial **passo a passo** para criar, do zero, um módulo que aparece
sozinho **no menu (sidebar)** e **no dashboard**, sem tocar no núcleo.

Vamos usar como exemplo um módulo mínimo chamado **Relatórios** (`slug`
`relatorios`). Adapte os nomes ao seu caso.

> Pré-requisitos: leia antes a [ARQUITETURA.md](ARQUITETURA.md) (registro de
> módulos e contrato do painel) e respeite os nomes/contratos da
> [SPEC.md](SPEC.md).

---

## Visão geral do que faremos

1. Criar o app em `apps/relatorios/`.
2. Registrar o app no `INSTALLED_APPS`.
3. Escrever o `AppConfig` e disparar o registro no `ready()`.
4. Criar o `modulo.py` com a subclasse de `ModuloBase`.
5. Definir `itens_menu` (sidebar) e `contexto_dashboard` (painel).
6. Criar `urls.py`, a view e o template.

O princípio-chave: **o núcleo nunca importa o seu módulo** — é o seu módulo que
se anuncia ao núcleo via o singleton `registro`.

---

## Passo 1 — Estrutura do app

Crie a pasta e os arquivos abaixo em `apps/relatorios/`:

```
apps/relatorios/
  __init__.py
  apps.py
  modulo.py
  urls.py
  views.py
  migrations/
    __init__.py
```

(Se o módulo tiver modelos, adicione também `models.py` e gere migrações.)

---

## Passo 2 — Registrar no `INSTALLED_APPS`

Em `config/settings.py`, acrescente o app à lista (depois de `apps.nucleo`):

```python
INSTALLED_APPS = [
    # ... apps do Django ...
    "apps.contas",
    "apps.nucleo",
    "apps.prospeccao",
    "apps.relatorios",   # <── novo módulo
]
```

Este é o **único** ponto do projeto "central" que você toca — e mesmo assim é só
registrar o app, como manda o Django. O núcleo continua sem conhecer o módulo.

---

## Passo 3 — `apps.py` e o `ready()`

O `AppConfig` importa o `modulo.py` no `ready()`. É esse import (com efeito
colateral de registro) que faz o módulo se anunciar ao núcleo.

```python
# apps/relatorios/apps.py
"""Configuração do app 'relatorios' (módulo plugável de exemplo)."""
from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("modulos.relatorios.apps")


class RelatoriosConfig(AppConfig):
    """AppConfig do módulo de relatórios (label implícito: ``relatorios``)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.relatorios"
    verbose_name = "Relatórios"

    def ready(self) -> None:
        """Registra o módulo no núcleo importando o ``modulo.py`` do app."""
        try:
            from apps.relatorios import modulo  # noqa: F401  (efeito: registro)
        except Exception:  # não impedir o boot por falha de registro
            logger.exception("Falha ao registrar o módulo de relatórios.")
```

> Garanta que `apps/relatorios/__init__.py` **não** force um `default_app_config`
> antigo; o Django 5 descobre o `AppConfig` automaticamente.

---

## Passo 4 e 5 — `modulo.py`: menu e dashboard

Aqui mora o coração do módulo. Estenda `ModuloBase` e registre com o decorator
`@registro.registrar`.

```python
# apps/relatorios/modulo.py
"""Registra o módulo de relatórios no núcleo (menu + painel)."""
from __future__ import annotations

import logging

from django.urls import NoReverseMatch, reverse

from apps.nucleo.modulos import ModuloBase, registro

logger = logging.getLogger("modulos.relatorios.modulo")


@registro.registrar
class ModuloRelatorios(ModuloBase):
    """Módulo mínimo de relatórios."""

    slug = "relatorios"
    nome = "Relatórios"
    icone = "relatorios"   # chave de ícone permitida (ver SPEC, seção 5)
    ordem = 20             # aparece depois de Prospecção (ordem=10)
    descricao = "Relatórios e indicadores consolidados."

    def url_inicial(self) -> str:
        """Item principal do módulo (name de URL)."""
        return "relatorios:inicio"

    def itens_menu(self, request) -> list[dict]:
        """Itens de sidebar — chaves EXATAS de ItemMenu."""
        rota_atual = self._rota_atual(request)
        return [
            {
                "rotulo": "Relatórios",
                "url": self._url_ou_hash("relatorios:inicio"),
                "icone": "relatorios",
                "ativo": rota_atual.startswith("relatorios:"),
            }
        ]

    def contexto_dashboard(self, request) -> dict:
        """Dados que este módulo injeta no painel.

        IMPORTANTE: use APENAS chaves NOVAS (com prefixo do módulo) para não
        sobrescrever as chaves do contrato da prospecção (seção 7 da SPEC). O
        merge do painel é raso: chaves iguais de módulos posteriores vencem.
        """
        try:
            return {
                "relatorios_total": 0,          # ex.: nº de relatórios gerados
                "relatorios_ultimo": "—",       # ex.: data do último relatório
            }
        except Exception:
            logger.exception("Falha no contexto_dashboard de relatorios.")
            return {}

    # -- auxiliares --------------------------------------------------------
    def _rota_atual(self, request) -> str:
        match = getattr(request, "resolver_match", None)
        return getattr(match, "view_name", "") or "" if match else ""

    def _url_ou_hash(self, nome_url: str) -> str:
        try:
            return reverse(nome_url)
        except NoReverseMatch:
            return "#"
```

### Regras de ouro do `contexto_dashboard`

- O núcleo já fornece **defaults zerados** para todas as chaves do contrato da
  seção 7. Se o seu módulo quiser **alimentar um card existente** (ex.:
  `total_empresas`), retorne aquela chave. Se quiser **dados próprios**, use
  chaves **novas com prefixo** (`relatorios_...`) para evitar colisão — o merge é
  raso e módulos de `ordem` maior sobrescrevem chaves iguais.
- Nunca deixe uma exceção escapar: retorne `{}` em caso de erro. O dashboard
  continua funcionando com os defaults.

### Ícones permitidos

A `icone` deve ser uma das chaves que a sidebar sabe mapear para um SVG (SPEC,
seção 5):

```
dashboard, prospeccao, conexoes, buscas, relatorios, perfil, config, sair,
empresa, alerta
```

A sidebar tolera um ícone desconhecido (usa um SVG genérico), mas prefira a
lista acima.

---

## Passo 6 — `urls.py`, view e template

### `urls.py` (com `app_name` = namespace)

```python
# apps/relatorios/urls.py
"""Rotas do módulo de relatórios. Namespace: 'relatorios'."""
from __future__ import annotations

from django.urls import path

from apps.relatorios import views

app_name = "relatorios"

urlpatterns = [
    path("", views.inicio, name="inicio"),
]
```

Inclua o app no roteador raiz, em `config/urls.py` (mantendo o dashboard por
último, na raiz):

```python
urlpatterns = [
    path(_prefixo_admin(), admin.site.urls),
    path("contas/", include(("apps.contas.urls", "contas"), namespace="contas")),
    path("prospeccao/", include(("apps.prospeccao.urls", "prospeccao"), namespace="prospeccao")),
    path("relatorios/", include(("apps.relatorios.urls", "relatorios"), namespace="relatorios")),  # <──
    path("", include(("apps.nucleo.urls", "nucleo"), namespace="nucleo")),
]
```

### `views.py` (protegida por admin)

Toda view do sistema exige `is_staff`. Use o decorator do app `contas` para FBVs
(ou o `AdminRequeridoMixin` para CBVs). O `SomenteAdminMiddleware` já protege
tudo, mas manter o decorator deixa a intenção explícita.

```python
# apps/relatorios/views.py
"""Views do módulo de relatórios (somente admin)."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.contas.decorators import admin_requerido


@admin_requerido
def inicio(request: HttpRequest) -> HttpResponse:
    """Página inicial do módulo de relatórios."""
    return render(request, "relatorios/inicio.html", {})
```

### Template (estende `base.html`)

Toda página interna estende `templates/base.html` e usa os blocos do contrato
(seção 4 da SPEC): `titulo`, `subtitulo`, `acoes_topo`, `conteudo`, `css_extra`,
`js_extra`.

```html
{# templates/relatorios/inicio.html #}
{% extends "base.html" %}
{% load nucleo_extras %}

{% block titulo %}{% texto "relatorios.inicio.titulo" %}{% endblock %}
{% block subtitulo %}{% texto "relatorios.inicio.subtitulo" %}{% endblock %}

{% block conteudo %}
  <section class="cartao">
    <h2 class="cartao__titulo">{% texto "relatorios.inicio.cartao_titulo" %}</h2>
    <p>Este é o módulo de relatórios de exemplo.</p>
  </section>
{% endblock %}
```

### Textos centralizados (`apps/nucleo/textos.py`)

Títulos, subtítulos, títulos de cartões, itens de menu, nome/descrição do
módulo e rótulos dos KPIs ficam **todos** no dicionário `TEXTOS` de
`apps/nucleo/textos.py` — a fonte única dos textos do sistema. Para o exemplo:

```python
# apps/nucleo/textos.py  (dentro de TEXTOS)
"relatorios": {
    "inicio": {
        "titulo": "Relatórios",
        "subtitulo": "Indicadores consolidados da operação",
        "cartao_titulo": "Em breve",
    },
},
# e em "modulos": {"relatorios": {"nome": "Relatórios", "descricao": "...", "menu": {...}}}
```

- **Templates:** `{% load nucleo_extras %}` e `{% texto "secao.pagina.chave" %}`.
  Variáveis: `{% texto "nucleo.dashboard.subtitulo" nome=request.user.nome_completo %}`
  (marcadores `{nome}` no texto). Para guardar em variável: `{% texto "x.y" as titulo %}`.
- **Python** (`modulo.py`, views, forms): `from apps.nucleo.textos import texto`
  e `texto("modulos.relatorios.nome")`.
- Chave inexistente não quebra a página (mostra o caminho e registra no log).
  Confira tudo com `python manage.py verificar_textos`.

---

## Passo 7 — Migrações (se houver modelos)

Se o módulo tiver `models.py`, gere e aplique as migrações:

```bash
python manage.py makemigrations relatorios
python manage.py migrate
```

---

## Passo 8 — Verificar

1. Rode `python manage.py runserver`.
2. Entre com um usuário admin.
3. O item **"Relatórios"** deve aparecer na sidebar; ao acessar
   `/relatorios/`, o item fica marcado como **ativo**.
4. No log do servidor, você verá `Módulo registrado: relatorios (Relatórios).`

Pronto — o módulo está plugado. Você **não** editou o `nucleo` em nenhum
momento: o único toque foi registrar o app no `INSTALLED_APPS` e no roteador
raiz, exatamente como o Django exige de qualquer app.

---

## Checklist rápido

- [ ] App criado em `apps/<slug>/` com `__init__.py` e `migrations/__init__.py`.
- [ ] App em `INSTALLED_APPS` (após `apps.nucleo`).
- [ ] `AppConfig` importa o `modulo.py` no `ready()`.
- [ ] `modulo.py` estende `ModuloBase` e usa `@registro.registrar`.
- [ ] `slug`, `nome`, `icone` (chave válida), `ordem`, `descricao` definidos.
- [ ] `itens_menu` retorna dicts com as chaves EXATAS `rotulo/url/icone/ativo`.
- [ ] `contexto_dashboard` usa chaves novas (com prefixo) e nunca deixa exceção
      escapar.
- [ ] `urls.py` com `app_name` = namespace; app incluído em `config/urls.py`.
- [ ] Views protegidas por `@admin_requerido` (FBV) ou `AdminRequeridoMixin` (CBV).
- [ ] Templates estendem `base.html` e usam os blocos do contrato.
- [ ] Textos (títulos, subtítulos, menus, KPIs) em `apps/nucleo/textos.py`;
      `python manage.py verificar_textos` sem chaves ausentes.
- [ ] Migrações geradas/aplicadas (se houver modelos).

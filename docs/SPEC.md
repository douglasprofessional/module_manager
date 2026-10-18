# SPEC — Fonte única de verdade (NÃO divergir)

Este documento define nomes, contratos e tokens que TODOS os arquivos devem respeitar
exatamente. Se algo não estiver aqui, siga o idioma PT-BR e o estilo do restante.

Alvo: Django 5.x, Python 3.11+. Windows/Linux. Sem dependência de Redis/Celery para rodar.

## 1. Estrutura de pastas (raiz = modulos/)

```
modulos/
  manage.py
  requirements.txt
  .env.example
  .gitignore
  config/            # pacote do projeto Django
    __init__.py  settings.py  urls.py  wsgi.py  asgi.py
  apps/
    __init__.py
    contas/          # autenticação (somente admin)
    nucleo/          # dashboard + registro de módulos (a BASE)
    prospeccao/      # 1º módulo
  templates/
  static/
  docs/
```

## 2. Nomes canônicos (usar exatamente)

- Pacote do projeto: `config`  → `DJANGO_SETTINGS_MODULE=config.settings`, `ROOT_URLCONF='config.urls'`.
- Apps (AppConfig.name / INSTALLED_APPS):
  - `apps.contas`  (label: `contas`)
  - `apps.nucleo`  (label: `nucleo`)
  - `apps.prospeccao` (label: `prospeccao`)
- Modelo de usuário: `AUTH_USER_MODEL = "contas.Usuario"`.
- Nome do sistema (marca exibida): **modulos**.
- Idioma: `LANGUAGE_CODE = "pt-br"`, `TIME_ZONE = "America/Sao_Paulo"`, `USE_TZ = True`.

## 3. URLs e names (namespaces)

config/urls.py inclui:
- `""`               -> include(("apps.nucleo.urls", "nucleo"))
- `"contas/"`        -> include(("apps.contas.urls", "contas"))
- `"prospeccao/"`    -> include(("apps.prospeccao.urls", "prospeccao"))
- `"admin/"`         -> admin.site.urls  (Django admin, prefixo alterável por env `DJANGO_ADMIN_URL`)

Names EXATOS:
- `nucleo:dashboard`         (rota `""`)
- `contas:login`            (rota `entrar/`)
- `contas:logout`           (rota `sair/`)
- `prospeccao:lista`        (rota `empresas/`)
- `prospeccao:detalhe`      (rota `empresas/<int:pk>/`)
- `prospeccao:conexoes`     (rota `conexoes/`)
- `prospeccao:nova_busca`   (rota `buscas/nova/`)
- `prospeccao:executar_busca` (rota `buscas/<int:pk>/executar/`, POST)

LOGIN_URL = "contas:login"; LOGIN_REDIRECT_URL = "nucleo:dashboard"; LOGOUT_REDIRECT_URL = "contas:login".

## 4. Template base — contrato de blocos

`templates/base.html` renderiza o LAYOUT (sidebar + topbar + área de conteúdo) e define:
- `{% block titulo %}` — vai no <title> e no <h1> do topo (o "Dashboard" grande).
- `{% block subtitulo %}` — linha cinza sob o título.
- `{% block acoes_topo %}` — canto direito do cabeçalho da página (ex.: seletor de datas).
- `{% block conteudo %}` — corpo principal.
- `{% block css_extra %}` e `{% block js_extra %}`.

A página de login (`contas/login.html`) NÃO estende base.html (tela cheia própria, mesmo tema).

Todas as páginas internas estendem `base.html`.

## 5. Context processor (navegação + marca)

`apps/nucleo/context_processors.py` → função `navegacao(request)` adicionada em
TEMPLATES.OPTIONS.context_processors. Retorna sempre:

```python
{
  "site_nome": "Gerenciador de Módulos",
  "modulos_menu": [ItemMenu, ...],   # itens vindos do registro de módulos
  "menu_conta": [ItemMenu, ...],     # Perfil, Configurações, Sair
  "rota_atual": request.resolver_match.view_name if resolver_match else "",
}
```

`ItemMenu` = dict com chaves EXATAS:
`{"rotulo": str, "url": str (já resolvida ou "#"), "icone": str, "ativo": bool}`

Chaves de ícone permitidas (o partial da sidebar mapeia string->SVG):
`dashboard, prospeccao, conexoes, buscas, relatorios, perfil, config, sair, empresa, alerta`.

O template da sidebar deve tolerar um ícone desconhecido (usa um SVG genérico).

## 6. Registro de módulos (o coração da BASE)

`apps/nucleo/modulos.py` expõe:
- classe `ModuloBase` com atributos de classe:
  `slug: str`, `nome: str`, `icone: str`, `ordem: int = 100`, `descricao: str = ""`.
  e métodos (todos opcionais de sobrescrever):
  - `itens_menu(self, request) -> list[dict]`  # ItemMenu(s) do módulo; padrão: 1 item com nome/icone/url via `url_inicial`
  - `url_inicial(self) -> str`  # name de url para o item principal; padrão "#"
  - `contexto_dashboard(self, request) -> dict`  # dados p/ o painel (ver seção 7); padrão {}
- objeto singleton `registro` (instância de `RegistroModulos`) com:
  - `registrar(classe_modulo)`  (decorator-friendly: retorna a classe)
  - `todos(self) -> list[ModuloBase]` (ordenado por `ordem`, depois `nome`)
  - `itens_menu(self, request) -> list[dict]` (concatena de todos)
  - `contexto_dashboard(self, request) -> dict` (faz merge raso dos dicts; ver 7)

Descoberta: cada app-módulo registra no seu `apps.py::ready()` importando seu `modulo.py`.
NUNCA importe `apps.prospeccao` dentro de `apps.nucleo` (o núcleo não conhece módulos).

## 7. Contrato do PAINEL (dashboard) — chaves EXATAS

`nucleo:dashboard` monta `painel` = defaults + merge de `contexto_dashboard` dos módulos.
`nucleo` fornece defaults zerados para TODAS as chaves abaixo (dashboard renderiza sem módulos).
`prospeccao.contexto_dashboard` preenche com dados reais (ou do seed).

```python
painel = {
  # Card 1 "Resumo de Prospecção" (analogia Balance Summary — gráfico de linha)
  "total_empresas": int,
  "novas_semana": int,
  "variacao_pct": float,             # ex.: 2.4  (exibe +2.4%)
  "serie_encontradas": list[int],    # ~8 pontos p/ a linha clara
  "serie_qualificadas": list[int],   # ~8 pontos p/ a linha roxa

  # Card 2 "Oportunidades" (analogia Spending — donut + legenda)
  "oportunidades_total": int,        # nº grande no centro do donut
  "oportunidades": list[dict],       # cada: {"rotulo": str, "pct": int, "cor": "#hex"}

  # Card 3 "Próximas ações" (analogia Upcoming payments)
  "proximas_acoes": list[dict],      # cada: {"quando": str, "titulo": str, "tag": str}

  # Card 4 "Empresas encontradas" (analogia Recent Transactions — TABELA principal)
  "empresas": list[dict],            # ver EmpresaLinha abaixo (EXATO)

  # Card 5 "Meta de prospecção" (analogia Saving Goal)
  "meta_atual": int,
  "meta_total": int,
  "meta_pct": int,                   # 0..100

  # Card 6 "Destaques" (analogia Investment Report)
  "destaque_titulo": str,
  "destaque_texto": str,
}
```

`EmpresaLinha` (dict) — chaves EXATAS exigidas pela regra do cliente:
```python
{
  "nome": str,
  "tempo_mercado": str,      # ex.: "12 anos" ou "Fundada em 2013" ou "—"
  "responsavel": str,        # fundador/CEO/contato comercial ou "—"
  "email": str,              # ou "—"
  "instagram": str,          # handle "@..." ou "—"
  "dominio": str,            # domínio da hospedagem ou "—"
  "whatsapp": str,           # "+55 ..." ou "—"
  "problemas": list[str],    # rótulos: "Sem site", "SEO fraco", "Sem SSL", ...
  "inicial": str,            # 2 letras p/ o avatar (ex.: "MC")
  "cor": str,                # "#hex" de fundo do avatar
  "pk": int | None,          # p/ link ao detalhe (None no modo demo)
}
```

## 8. Tokens de design (CSS variables) — replicar o print

Definir em `static/css/dashboard.css` no `:root`:
```
--fundo: #0a0a0b;            /* fundo geral quase preto */
--superficie: #141417;      /* cards */
--superficie-2: #1b1b20;    /* itens dentro do card / hovers */
--borda: #26262c;
--texto: #f4f4f5;
--texto-suave: #a1a1aa;
--texto-fraco: #6b7280;
--roxo: #7c5cff;            /* accent principal */
--roxo-2: #9b7dff;
--grad-roxo: linear-gradient(135deg,#7c5cff,#5b3df0);
--verde: #34d399;  --vermelho: #f87171;  --azul: #38bdf8;  --amarelo: #fbbf24; --creme:#f5e6c8;
--raio: 22px;               /* raio dos cards */
--raio-sm: 14px;
--sombra: 0 10px 30px rgba(0,0,0,.35);
```
Tipografia: fonte sistema + fallback; títulos com peso 700 e leve arredondamento
(usar `font-family` com "Poppins" opcional via @import COMENTADO — não depender de CDN externa por CSP).
Na verdade: usar SOMENTE fontes do sistema (sem @import externo) por causa da CSP.

Layout: grid com sidebar fixa ~248px + conteúdo. Cards em grid responsivo.
Sidebar item ativo = fundo `--grad-roxo`, texto branco, cantos arredondados.
Ícones: quadradinho ~40px, fundo roxo translúcido `rgba(124,92,255,.15)`, ícone roxo.

## 9. Segurança (obrigatório em TODOS os pontos)

- `contas.Usuario`: AbstractBaseUser + PermissionsMixin, login por e-mail, `is_staff` obrigatório
  para acessar o sistema. Manager cria superuser. Sem usuário anônimo em nada além do login.
- Middleware `apps.contas.middleware.SomenteAdminMiddleware`: exige `is_authenticated and is_staff`
  em todas as rotas exceto login/logout/admin/estáticos; senão redireciona p/ login.
- Throttling de login: `apps.contas` guarda tentativas por (ip+email) em cache; bloqueia após 5 falhas
  por 15 min. Não revelar se e-mail existe (mensagem genérica).
- Settings dependentes de ambiente via `os.environ` (usar `python-dotenv` para ler `.env`):
  `SECRET_KEY`, `DEBUG` (default False), `ALLOWED_HOSTS`, `DJANGO_ADMIN_URL`, `modulos_FERNET_KEY`,
  `GOOGLE_MAPS_API_KEY` (fallback), `GOOGLE_PAGESPEED_API_KEY`.
- Produção (DEBUG=False): `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`,
  `X_FRAME_OPTIONS="DENY"`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY="same-origin"`,
  `SESSION_COOKIE_HTTPONLY=True`, `CSRF_COOKIE_HTTPONLY=False` (padrão), `SESSION_EXPIRE_AT_BROWSER_CLOSE`.
- CSP simples via middleware próprio `apps.nucleo` OU cabeçalho manual (sem lib externa):
  default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'.
  (JS e CSS servidos localmente; nada de CDN.)
- Criptografia de segredos: `apps/nucleo/criptografia.py` com `criptografar(txt)->str` e
  `descriptografar(txt)->str` usando `cryptography.fernet.Fernet` e `modulos_FERNET_KEY`.
  Se a chave não existir em DEBUG, derivar uma efêmera de SECRET_KEY e AVISAR no log.
- **Anti-SSRF** em `apps/prospeccao/services/seguranca_rede.py`:
  função `requisicao_segura(url, ...)` que: valida esquema http/https; resolve o host;
  recusa IPs privados/loopback/link-local/reservados (usar `ipaddress`); timeout curto;
  limite de tamanho de resposta (ex.: 2 MB); `allow_redirects=False` e valida cada salto manualmente;
  User-Agent próprio; nunca segue para IP interno. Usada por TODO fetch de sites de terceiros.
- Auditoria: `apps/nucleo/models.py::RegistroAuditoria` (usuario, acao, objeto, ip, quando).
- Sem segredos hardcoded. ORM sempre (sem SQL cru). Autoescape dos templates mantido.

## 10. Dependências (requirements.txt)

```
Django>=5.0,<6.0
python-dotenv>=1.0
requests>=2.31
cryptography>=42.0
tldextract>=5.1
gunicorn>=21.2         # produção
whitenoise>=6.6        # servir estáticos em produção
```
(Google Places/PageSpeed acessados via `requests` direto — sem SDK pesado. `python-whois`
é OPCIONAL e NÃO entra em requirements para não quebrar instalação; o serviço de enriquecimento
usa BrasilAPI via requests e degrada com elegância.)

## 11. Módulo Prospecção — modelos (apps/prospeccao/models.py)

- `ConexaoGoogle`: nome, `chave_api_criptografada`(TextField), ativo, criado_por(FK Usuario),
  criado_em, atualizado_em. Property `chave_api` que descriptografa; setter que criptografa.
  Nunca expor a chave em texto no admin/serializers.
- `Busca`: conexao(FK), termo, localizacao, raio_metros(int), status(enum:
  pendente/executando/concluida/erro), total_resultados(int default 0), criado_por(FK), criado_em.
- `Empresa`: busca(FK null), place_id(unique null), nome, categoria, endereco, telefone,
  whatsapp, email, instagram, website, dominio, tem_site(bool), site_desatualizado(bool),
  apenas_instagram(bool), tem_ssl(bool null), hospedagem_sem_site(bool),
  score_seo(int null 0..100), score_performance(int null 0..100),
  data_fundacao(date null), tempo_mercado_texto, responsavel, cargo_responsavel,
  latitude/longitude(null), status_prospeccao(enum: nova/qualificada/contatada/descartada),
  oportunidade_score(int 0..100), observacoes, criado_em, atualizado_em.
  Método `linha_dashboard(self) -> EmpresaLinha` (dict da seção 7).
  Método `rotulos_problemas(self) -> list[str]`.

Enums via `models.TextChoices` com rótulos PT-BR.

## 12. Serviços prospecção (apps/prospeccao/services/)

- `google_places.py`: `buscar_empresas(chave, termo, local, raio)` e `detalhes(chave, place_id)`
  via Places API (Text Search + Place Details) com `requests`. Tratar ausência de chave -> erro claro.
- `seguranca_rede.py`: fetcher anti-SSRF (seção 9).
- `analise_site.py`: baixa HTML (via fetcher seguro) e avalia: título/description/H1 (SEO),
  presença de conteúdo x "só link de Instagram", sinais de desatualização (ex.: ano antigo no rodapé,
  ausência de viewport), extrai email/instagram/whatsapp (regex) e domínio.
- `pagespeed.py`: `pontuar(url, chave)` via PageSpeed Insights API (degrada p/ None sem chave).
- `enriquecimento.py`: BrasilAPI CNPJ (quando houver CNPJ) p/ data de fundação e sócios; helpers
  p/ tempo de mercado e escolha de responsável. Degrada com elegância.
- `orquestrador.py`: `analisar_empresa(empresa, conexao)` — orquestra tudo, calcula flags,
  `oportunidade_score` e salva. Idempotente e resiliente a exceções por etapa.
- Comando `seed_prospeccao` cria ConexaoGoogle demo + Empresas exemplo (dados fictícios BR)
  para popular o dashboard SEM chamadas externas.

## 13. Views/permytemplates prospecção

- Todas as views exigem admin (usar mixin `apps.contas.mixins.AdminRequeridoMixin` para CBVs
  e/ou `@apps.contas.decorators.admin_requerido` para FBVs).
- `lista`: tabela paginada com as 7 colunas obrigatórias + filtros (problema/status).
- `detalhe`: ficha completa da empresa.
- `conexoes`: lista/cria ConexaoGoogle (chave via form; salva criptografada).
- `nova_busca` + `executar_busca` (POST, CSRF): dispara orquestrador (síncrono; estrutura
  pronta p/ mover a Celery em tasks.py).

## 14. Convenções de código

- PT-BR em identificadores de domínio, textos e docstrings; manter termos Django em inglês
  quando forem API do framework.
- Type hints onde ajudar. Funções pequenas. Sem `print` (usar `logging`).
- Cada arquivo Python começa com docstring curta explicando o papel.
- `from __future__ import annotations` no topo dos módulos de serviço.

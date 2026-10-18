# Segurança do modulos

Este documento lista as **medidas de segurança** implementadas no modulos
(conforme a seção 9 da [SPEC.md](SPEC.md)), onde cada uma vive no código, e traz
um **checklist de deploy seguro**.

Princípios gerais adotados em todo o projeto:

- **Sem segredos hardcoded** — todo segredo vem do ambiente (`.env`).
- **ORM sempre** — nenhuma consulta SQL crua.
- **Autoescape de templates** mantido (proteção contra XSS por padrão do Django).
- **`logging`, nunca `print`** — e segredos nunca vão para o log.

---

## 1. Acesso somente para administradores

- **Modelo de usuário** (`apps/contas/models.py::Usuario`): `AbstractBaseUser` +
  `PermissionsMixin`, **login por e-mail** (`USERNAME_FIELD = "email"`), senha
  sempre em **hash** (`set_password`). `is_staff` é o campo que libera o acesso
  ao sistema. O manager (`managers.py`) cria usuário e superusuário; superusuário
  exige `is_staff=True` e `is_superuser=True`.
- **Middleware `SomenteAdminMiddleware`** (`apps/contas/middleware.py`): exige
  `is_authenticated and is_staff` em **todas** as rotas, exceto login, logout,
  admin do Django e arquivos estáticos/mídia. Caso contrário, redireciona para o
  login preservando o `?next=`. As isenções são calculadas via `reverse` (e
  refletem o prefixo real do admin, mesmo alterado por env).
- **Mixin e decorator** (`apps/contas/mixins.py::AdminRequeridoMixin` e
  `apps/contas/decorators.py::admin_requerido`): reforçam a mesma regra
  diretamente nas CBVs e FBVs, deixando a intenção explícita (defesa em
  profundidade).

---

## 2. Throttling de login

Em `apps/contas/views.py`:

- Conta as tentativas por chave **(IP + e-mail)** no cache
  (`django.core.cache`), com a chave "hasheada" (SHA-256) antes de ir ao backend.
- **Bloqueia após 5 falhas** (`LIMITE_TENTATIVAS = 5`) por **15 minutos**
  (`JANELA_BLOQUEIO_SEGUNDOS = 15*60`). Quando bloqueado, responde **HTTP 429**.
- **Não revela se o e-mail existe**: mensagem genérica em qualquer falha.
- Em sucesso, limpa o contador e **cicla a sessão** (`auth_login` protege contra
  *session fixation*); registra o último IP do usuário.
- O IP vem de `REMOTE_ADDR` (não confia em cabeçalhos de proxy por padrão).

O backend de cache padrão é `LocMemCache` (`config/settings.py`) — ótimo para
`runserver` (um processo). **Atenção:** com múltiplos workers (ex.: Gunicorn
`--workers 3`) o `LocMemCache` não é compartilhado e o contador de tentativas
fica por-processo, enfraquecendo o bloqueio. Em produção defina
`CACHE_BACKEND=db` (DatabaseCache, compartilhado entre workers — o entrypoint
Docker já roda `createcachetable`; no VPS nativo rode-o uma vez) ou
`CACHE_BACKEND=redis` com `REDIS_URL`. O `docker-compose.yml` já usa `db`.

---

## 3. Cookies, HSTS, redirect SSL e cabeçalhos

Em `config/settings.py` (aplicados quando `DEBUG=False`, seção 9 da SPEC):

- `SECURE_SSL_REDIRECT = True` — força HTTPS.
- `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True` — cookies só por
  HTTPS.
- `SECURE_HSTS_SECONDS = 31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`,
  `SECURE_HSTS_PRELOAD = True` — HSTS (1 ano).
- `SECURE_CONTENT_TYPE_NOSNIFF = True`.
- `SECURE_REFERRER_POLICY = "same-origin"`.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`.
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` — detecta HTTPS
  atrás de proxy/CDN.

Válidos em **qualquer** modo:

- `SESSION_COOKIE_HTTPONLY = True`.
- `CSRF_COOKIE_HTTPONLY = False` (padrão do Django; scripts próprios podem ler o
  token para requisições AJAX).
- `X_FRAME_OPTIONS = "DENY"` (via `XFrameOptionsMiddleware`) — anti-clickjacking.

### CSP e demais cabeçalhos (`apps/nucleo/middleware.py`)

O `CabecalhosSegurancaMiddleware` aplica, em toda resposta, uma **CSP simples
sem CDN** (tudo servido localmente):

```
Content-Security-Policy:
  default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'
```

E ainda: `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` e
`Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`. Usa
`setdefault` para não sobrescrever cabeçalhos já definidos por outros
middlewares.

> Como a CSP proíbe CDNs externas, **todo CSS/JS é local** (em `static/`) e a
> tipografia usa **apenas fontes do sistema** (sem `@import` externo).

---

## 4. Criptografia de segredos (Fernet)

`apps/nucleo/criptografia.py` expõe `criptografar(txt) -> str` e
`descriptografar(txt) -> str` usando `cryptography.fernet.Fernet` com a chave
`modulos_FERNET_KEY`.

- As **chaves de API do Google** são guardadas **cifradas** no banco: o modelo
  `ConexaoGoogle` (`apps/prospeccao/models.py`) tem `chave_api_criptografada`
  (TextField) e a property `chave_api` que **decifra sob demanda** (o setter
  cifra). A chave **nunca** é exposta em texto no admin nem em serializações; há
  a property `tem_chave` para indicar presença sem revelar o valor.
- Em **produção** (`DEBUG=False`), `modulos_FERNET_KEY` é **obrigatória**
  (levanta `ImproperlyConfigured` se faltar).
- Em **desenvolvimento** (`DEBUG=True`), se ausente, uma chave **efêmera** é
  derivada do `SECRET_KEY` (SHA-256 → base64 urlsafe), **com aviso no log**.
  Atenção: a chave efêmera muda se o `SECRET_KEY` mudar, invalidando os segredos
  já cifrados — por isso serve **apenas** para dev.

---

## 5. Anti-SSRF no fetcher de sites

**Todo** acesso a sites de terceiros passa por
`apps/prospeccao/services/seguranca_rede.py::requisicao_segura` — **nunca**
`requests.get` direto. Defesas:

- Aceita **apenas** esquemas `http`/`https`.
- Resolve o host (`socket.getaddrinfo`) e **recusa** se **qualquer** IP for
  privado, loopback, link-local, reservado, multicast, não especificado ou de
  faixas especiais (CGNAT `100.64/10`, TEST-NET, benchmarking, classe E,
  `0.0.0.0/8`...). Também trata literais de IP e IPv6 que mapeiam IPv4.
- `allow_redirects=False`: **cada salto** de redirecionamento é **revalidado**
  (re-resolve e re-checa o IP) antes de ser seguido; há limite de saltos.
- **Timeout curto** e **limite de tamanho** da resposta (padrão **2 MB**), lendo
  em *stream* e cortando o excedente.
- **User-Agent próprio** `modulosBot/1.0`.
- Função `verificar_ssl` aplica a mesma checagem anti-SSRF antes do handshake
  TLS.

> Nota honesta (documentada no próprio módulo): entre a resolução de checagem e a
> conexão do `requests` existe uma janela TOCTOU (*DNS rebinding*). A validação
> por salto reduz muito a superfície; para ambientes de altíssimo risco, o ideal
> é fixar o IP validado na conexão.

---

## 6. Auditoria

`apps/nucleo/models.py::RegistroAuditoria` é uma trilha **append-only** (quem,
ação, objeto, IP, quando; ordenada do mais recente ao mais antigo). O `usuario`
é `SET_NULL` para preservar o histórico mesmo se a conta for removida. Nenhum
campo contém segredos em texto.

Eventos registrados incluem: login, logout e tentativas de login
(`apps/contas/views.py`); criação de conexão, criação e execução de busca
(`apps/prospeccao/views.py`). A auditoria é *best-effort*: nunca quebra o fluxo
principal.

---

## 7. Segredos em `.env` e ORM/autoescape

- Segredos e configuração sensível vêm de variáveis de ambiente, lidas via
  `python-dotenv` (`config/settings.py`): `SECRET_KEY`, `DEBUG`,
  `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DJANGO_ADMIN_URL`,
  `modulos_FERNET_KEY`, `GOOGLE_MAPS_API_KEY`, `GOOGLE_PAGESPEED_API_KEY` e a
  opcional `DATABASE_URL`.
- O `.env` está no **`.gitignore`** (apenas o `.env.example` é versionado).
- **ORM sempre** — sem SQL cru; as consultas do dashboard usam agregações do ORM.
- **Autoescape** dos templates mantido — proteção padrão contra XSS.
- Chamadas às APIs do Google **nunca logam a chave** (ela trafega só no cabeçalho
  `X-Goog-Api-Key`; a query do PageSpeed, que contém a chave, não é logada).

---

## Checklist de deploy seguro

Antes de expor o modulos em produção, confirme:

- [ ] **`DEBUG=False`** no ambiente.
- [ ] **`SECRET_KEY`** forte e única definida por env (gerada com
      `get_random_secret_key`); nunca a de desenvolvimento.
- [ ] **`modulos_FERNET_KEY`** definida por env (gerada com
      `Fernet.generate_key()`), **persistente** e guardada com segurança.
- [ ] **`ALLOWED_HOSTS`** com os domínios reais (sem curinga aberto).
- [ ] **`CSRF_TRUSTED_ORIGINS`** com os domínios **com esquema** (`https://...`).
- [ ] **HTTPS** ativo (certificado válido); com `DEBUG=False` o app já força
      redirect SSL, HSTS e cookies `Secure`.
- [ ] **`DJANGO_ADMIN_URL`** trocado para um prefixo difícil de adivinhar.
- [ ] **Coleta de estáticos**: `python manage.py collectstatic` (WhiteNoise
      serve os arquivos com `CompressedManifestStaticFilesStorage`).
- [ ] **Servidor de aplicação** adequado (ex.: `gunicorn`), atrás de um proxy
      reverso; confirmar `SECURE_PROXY_SSL_HEADER` compatível com o proxy.
- [ ] **Cache compartilhado** (Redis/Memcached) se houver múltiplos
      processos/instâncias, para o throttling de login valer globalmente.
- [ ] **Banco de dados** de produção (ex.: PostgreSQL via `DATABASE_URL`), com
      backups; tratar o banco como sensível (contém segredos cifrados).
- [ ] **Superusuário** criado com senha forte (`createsuperuser`).
- [ ] **`.env` fora do controle de versão** e com permissões restritas no
      servidor.
- [ ] **Chaves de API do Google restritas** (por API e, se possível, por IP) no
      Google Cloud Console.
- [ ] **Rotação de chaves** planejada:
      - `SECRET_KEY`: invalida sessões ao trocar (usuários refazem login).
      - `modulos_FERNET_KEY`: ao rotacionar, **re-cifre** os segredos
        existentes (decifrar com a chave antiga e cifrar com a nova) antes de
        remover a antiga — caso contrário as chaves de API guardadas ficam
        ilegíveis.
      - Chaves de API do Google: revogue/rotacione periodicamente no Console.
- [ ] **Logs** monitorados; confirmar que nenhum segredo aparece neles.

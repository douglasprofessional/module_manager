# SPEC ADENDO 3 — Módulo Marketing por E-mail (NÃO divergir)

Complementa `docs/SPEC.md`, `docs/SPEC_MODULOS.md` e `docs/SPEC_MODULOS_2.md`. Vale TUDO deles
(nomes, segurança seção 9, PT-BR em TODO texto/conteúdo, logging, docstrings,
`from __future__ import annotations`, only-admin, CSRF em POST, migrações só `__init__.py`).

ANTES de escrever, LEIA e IMITE os padrões já aprovados:
- `apps/nucleo/modulos.py` (ModuloBase, cards_resumo), `apps/nucleo/criptografia.py` (Fernet),
- `apps/prospeccao/models.py::ConexaoGoogle` (campo cifrado `*_criptografada` + property que cifra/decifra),
- `apps/monitoramento/{models,forms,views,modulo,apps,urls,admin}.py` e `services/ssh_coletor.py`,
- `apps/monitoramento/management/commands/seed_monitoramento.py`,
- `templates/base.html`, `templates/contas/login.html` (página STANDALONE, não estende base),
- `templates/monitoramento/detalhe.html` (confirmação via `data-confirmar` + JS, sem onsubmit inline),
- `templates/parciais/_icones.html`, `static/css/dashboard.css` (design system).

Regras comuns: ready() registra o módulo; related_name ÚNICO; auditoria via
`apps.nucleo.models.RegistroAuditoria(objeto_repr=(x or "")[:255], ip=REMOTE_ADDR)`; CSS próprio em
`static/email_marketing/email_marketing.css` (usa variáveis globais); templates estendem base.html
(exceto a página pública de descadastro); `cards_resumo` no formato EXATO
`{"rotulo","valor","detalhe","icone","cor":"#hex","url"}`.

JÁ FEITO PARA VOCÊ (não altere): `apps.email_marketing` em INSTALLED_APPS; `path("email-marketing/", ...)`
com namespace `email_marketing` em config/urls.py; `settings.PUBLIC_URL_PREFIXES` inclui
`/email-marketing/descadastrar/` e o `SomenteAdminMiddleware` isenta esses prefixos; `settings.SITE_URL`
existe (base absoluta para links de e-mail); ícones `megafone`, `enviar`, `grupo` adicionados a `_icones.html`.

=================================================================================
## MÓDULO 5 — MARKETING POR E-MAIL (app apps.email_marketing, ns "email_marketing", ícone "megafone", ordem 60)
=================================================================================

Objetivo (autocontido): cadastrar o **e-mail remetente** e a **configuração SMTP** DENTRO do módulo e
enviar **campanhas em massa** por esse remetente — sem depender de serviço externo nem das configs globais
`EMAIL_*` do Django. Toda a solução de envio é o próprio módulo.

Arquivos a criar (SOMENTE estes):
- apps/email_marketing/__init__.py
- apps/email_marketing/apps.py           (EmailMarketingConfig, name="apps.email_marketing", ready() importa modulo)
- apps/email_marketing/models.py
- apps/email_marketing/modulo.py
- apps/email_marketing/forms.py
- apps/email_marketing/views.py
- apps/email_marketing/urls.py
- apps/email_marketing/admin.py
- apps/email_marketing/services/__init__.py
- apps/email_marketing/services/enviador.py
- apps/email_marketing/migrations/__init__.py
- apps/email_marketing/management/__init__.py
- apps/email_marketing/management/commands/__init__.py
- apps/email_marketing/management/commands/seed_email_marketing.py
- templates/email_marketing/campanhas.html
- templates/email_marketing/campanha_form.html
- templates/email_marketing/campanha_detalhe.html
- templates/email_marketing/configuracoes.html
- templates/email_marketing/contatos.html
- templates/email_marketing/listas.html
- templates/email_marketing/descadastrar.html     (STANDALONE — NÃO estende base.html; tema escuro, como login)
- static/email_marketing/email_marketing.css
- static/email_marketing/email_marketing.js       (confirmação data-confirmar + toggle de campos SMTP; sem libs/CDN)

### Modelos (models.py)

- `ConfiguracaoEnvio` — o REMETENTE + SMTP (a "conta de envio"):
  - nome(CharField 120), 
  - tipo(TextChoices: SMTP="smtp", CONSOLE="console" — "Console (teste)"; default CONSOLE),
  - email_remetente(EmailField — o endereço que aparece no "De"),
  - nome_remetente(CharField 120 blank — nome exibido),
  - responder_para(EmailField blank — Reply-To),
  - host(CharField 255 blank), porta(PositiveIntegerField default 587),
  - usuario(CharField 255 blank),
  - senha_criptografada(TextField blank default ""),  # Fernet; property `senha` (getter decifra/setter cifra, preserva conteúdo)
  - usar_tls(Bool default True), usar_ssl(Bool default False),
  - ativo(Bool default True),
  - criado_por(FK AUTH_USER_MODEL SET_NULL null blank related_name="config_envio_email"),
  - criado_em(auto_now_add), atualizado_em(auto_now).
  - Property `senha`/`senha.setter` cifrando via apps.nucleo.criptografia (NÃO faz strip do conteúdo; só decide limpar por presença). `tem_senha` (bool) sem revelar.
  - `remetente_formatado()` -> "Nome <email>" (usa email_marketing.utils? não; método do modelo). Use email.utils.formataddr.
  - `abrir_conexao()` -> conexão de e-mail do Django:
      * tipo CONSOLE -> `django.core.mail.get_connection("django.core.mail.backends.console.EmailBackend")`
        (imprime no stdout/log — ideal para TESTAR localmente sem SMTP real);
      * tipo SMTP -> `get_connection("django.core.mail.backends.smtp.EmailBackend", host=host, port=porta,
        username=usuario, password=self.senha, use_tls=usar_tls, use_ssl=usar_ssl, timeout=20)`.
    NUNCA logar a senha. Validar mutualmente exclusivo TLS/SSL no form.
  - `__str__` = f"{nome} <{email_remetente}>".

- `Contato`:
  - email(EmailField unique), nome(CharField 150 blank), empresa(CharField 150 blank), tags(CharField 200 blank),
  - inscrito(Bool default True), descadastrado_em(DateTimeField null blank),
  - token_descadastro(CharField 64 unique, db_index) — gerado com `secrets.token_urlsafe(32)` no save() se vazio,
  - origem(CharField 80 blank), criado_em(auto_now_add).
  - Método `descadastrar()` (marca inscrito=False + descadastrado_em=now, idempotente).
  - Método `iniciais()`/`primeiro_nome()` p/ exibição e personalização.
  - Meta ordering ("email",).

- `Lista`:
  - nome(CharField 120), descricao(TextField blank), contatos(M2M Contato, blank, related_name="listas"),
    criado_em(auto_now_add). Meta ordering ("nome",).
  - Método `destinatarios()` -> contatos com inscrito=True (queryset). __str__=nome.

- `Campanha`:
  - nome(CharField 160), assunto(CharField 200),
  - corpo_html(TextField), corpo_texto(TextField blank — alternativa em texto puro; se vazio, derivar do html com strip_tags),
  - configuracao(FK ConfiguracaoEnvio PROTECT related_name="campanhas"),
  - lista(FK Lista SET_NULL null blank related_name="campanhas" — null = TODOS os contatos inscritos),
  - status(TextChoices: RASCUNHO/ENVIANDO/ENVIADA/PARCIAL/ERRO; default RASCUNHO),
  - total_destinatarios/total_enviados/total_falhas(PositiveIntegerField default 0),
  - criado_por(FK AUTH_USER_MODEL SET_NULL null blank related_name="campanhas_email"),
  - criado_em(auto_now_add), enviada_em(DateTimeField null blank).
  - `destinatarios()` -> lista.destinatarios() ou Contato.objects.filter(inscrito=True).
  - `classe_status()` -> tag-status--* (rascunho->neutro/pendente, enviando->executando, enviada->concluida, parcial->pendente, erro->erro).
  - `pode_enviar()` -> status in (RASCUNHO, ERRO, PARCIAL). Meta ordering ("-criado_em",).

- `EnvioEmail` (log por destinatário):
  - campanha(FK Campanha CASCADE related_name="envios"), contato(FK Contato SET_NULL null related_name="envios"),
  - email(CharField 254 — snapshot), status(TextChoices: PENDENTE/ENVIADO/FALHA; default PENDENTE),
  - erro(CharField 255 blank), enviado_em(DateTimeField null blank), criado_em(auto_now_add).
  - Meta ordering ("-criado_em",).

### Serviço de envio (services/enviador.py) — o CORAÇÃO da solução

- `render_personalizado(texto, contato, link_descadastro, html: bool) -> str`:
  substituição SIMPLES (str.replace) dos marcadores `{{ nome }}`, `{{ email }}`, `{{ empresa }}`,
  `{{ link_descadastro }}` (aceite com e sem espaços: `{{nome}}` e `{{ nome }}`). Para `html=True`,
  ESCAPAR os valores do contato com `django.utils.html.escape` (evita quebrar/injewtar HTML a partir de
  dados do contato); o link_descadastro entra como URL. NÃO usar o motor de template do Django no corpo
  (evita SSTI); apenas replace.
- `enviar_teste(configuracao, destinatario) -> tuple[bool, str]`:
  abre a conexão da configuração e envia 1 e-mail de teste; retorna (ok, mensagem). Nunca lança; nunca loga senha.
- `enviar_campanha(campanha) -> dict`:
  * se not campanha.pode_enviar(): retorna erro "estado inválido";
  * status=ENVIANDO (save); zera contadores; abre `campanha.configuracao.abrir_conexao()`;
  * destinatarios = campanha.destinatarios(); total_destinatarios = count;
  * para cada contato (em lote; use `conn` reutilizada):
      - link_descadastro = f"{settings.SITE_URL.rstrip('/')}" + reverse("email_marketing:descadastrar", args=[contato.token_descadastro]);
      - assunto = render_personalizado(assunto, contato, link, html=False);
      - texto = render_personalizado(corpo_texto or strip_tags(corpo_html), contato, link, html=False);
      - html = render_personalizado(corpo_html, contato, link, html=True);
      - msg = EmailMultiAlternatives(assunto, texto, from_email=config.remetente_formatado(),
              to=[contato.email], reply_to=[config.responder_para] if config.responder_para else None, connection=conn);
        msg.attach_alternative(html, "text/html");
      - try: msg.send(); cria EnvioEmail(status=ENVIADO, enviado_em=now); total_enviados++
        except Exception: cria EnvioEmail(status=FALHA, erro=tipo genérico[:255]); total_falhas++; loga sem segredo.
  * fecha a conexão (finally); status = ENVIADA (se 0 falhas) / PARCIAL (se algumas) / ERRO (se todas falharam ou exceção geral); enviada_em=now; save contadores; retorna resumo.
  * Resiliente por destinatário; NUNCA loga a senha SMTP.
- Teto/observação: envio SÍNCRONO (roda no request), isolado e pronto para Celery. Documente que listas
  muito grandes devem usar um worker no futuro.

### Views (views.py)

Todas admin (AdminRequeridoMixin nas CBV; @admin_requerido + @csrf_protect + @require_POST nas ações),
EXCETO `descadastrar` (PÚBLICA). Auditoria nas ações que criam/enviam.

- `CampanhaListView` (ListView, paginação): lista campanhas com status e contadores.
- `campanha_nova` (GET/POST): CampanhaForm; criado_por=user; status RASCUNHO.
- `CampanhaDetailView`: mostra a campanha, os contadores, amostra de EnvioEmail, e botões "Enviar" e
  (opcional) prévia. Passa o nº de destinatários calculado.
- `campanha_enviar` (POST): chama enviador.enviar_campanha(campanha) SINCRONAMENTE; messages com resultado.
- `configuracoes` (GET/POST): lista ConfiguracaoEnvio + cria nova (ConfiguracaoEnvioForm; senha cifrada).
- `config_testar` (POST): recebe `destinatario` (EmailField validado) e chama enviador.enviar_teste; messages.
- `contatos` (GET/POST): lista Contato (paginada) + adiciona em massa: um Textarea com e-mails (um por linha,
  aceitar "Nome <email>" simples); valida cada e-mail (django.core.validators) e faz get_or_create; ignora inválidos
  com aviso. Também permite marcar/desmarcar inscrito no admin.
- `listas` (GET/POST): lista Lista + cria (ListaForm; seleção de contatos via ModelMultipleChoiceField).
- `descadastrar` (PÚBLICA, GET+POST):
    * GET: procura Contato por token_descadostro; se não achar -> página "link inválido"; se achar ->
      página de CONFIRMAÇÃO (mostra o e-mail) com um form POST (CSRF).
    * POST: confirma e chama contato.descadastrar(); mostra "descadastrado com sucesso".
    * SEM login (isenta pelo PUBLIC_URL_PREFIXES). Só marca descadastro; nenhuma outra ação; sem enumeração
      (token grande/aleatório). Página STANDALONE (não estende base.html).

### modulo.py (ModuloEmailMarketing)
- slug="email_marketing", nome="Marketing", icone="megafone", ordem=60, descricao PT-BR.
- url_inicial -> "email_marketing:campanhas".
- itens_menu: "Campanhas" (megafone, rotas {campanhas, campanha_nova, campanha_detalhe}),
  "Contatos" (grupo, {contatos, listas}), "Configurações de envio" (config, {configuracoes}).
- cards_resumo (try/except -> []): 3 KPIs:
  {"Campanhas enviadas": Campanha.objects.filter(status__in=[ENVIADA, PARCIAL]).count(), icone "megafone", cor "#7c5cff", url campanhas},
  {"Contatos inscritos": Contato.objects.filter(inscrito=True).count(), icone "grupo", cor "#34d399", url contatos},
  {"E-mails enviados": EnvioEmail.objects.filter(status=ENVIADO).count(), icone "enviar", cor "#38bdf8", url campanhas, detalhe "total"}.
- contexto_dashboard -> {}.

### forms.py
- ConfiguracaoEnvioForm (ModelForm): campos nome, tipo, email_remetente, nome_remetente, responder_para,
  host, porta, usuario, usar_tls, usar_ssl, ativo + campo EXTRA `senha` (PasswordInput, required=False,
  strip=False) que no save cifra via property (em branco ao editar = manter). clean(): se tipo=SMTP exigir host
  e email_remetente; TLS e SSL não podem ambos True.
- CampanhaForm (nome, assunto, corpo_html, corpo_texto, configuracao, lista). Textareas para os corpos.
- ContatoImportacaoForm (Textarea `emails`) + validação linha a linha.
- ListaForm (nome, descricao, contatos ModelMultipleChoiceField).

### urls.py (app_name="email_marketing"), names EXATOS:
- "" -> campanhas ; "campanhas/nova/" -> campanha_nova ; "campanhas/<int:pk>/" -> campanha_detalhe ;
- "campanhas/<int:pk>/enviar/" -> campanha_enviar (POST) ;
- "configuracoes/" -> configuracoes ; "configuracoes/<int:pk>/testar/" -> config_testar (POST) ;
- "contatos/" -> contatos ; "listas/" -> listas ;
- "descadastrar/<str:token>/" -> descadastrar (GET/POST público).

### admin.py
ConfiguracaoEnvio (NUNCA expor senha; readonly em senha_criptografada ou exclua), Contato, Lista, Campanha, EnvioEmail
(readonly). list_display úteis.

### seed_email_marketing.py (idempotente, SEM rede)
- Cria 1 ConfiguracaoEnvio tipo CONSOLE "Remetente de Teste (Console)" com email_remetente "no-reply@modulos.local"
  (assim o envio local IMPRIME no log em vez de exigir SMTP real).
- Cria ~6 Contatos fictícios (inscritos) e 1 Lista "Clientes (demo)" com esses contatos.
- Cria 1 Campanha RASCUNHO "Novidades de {mês}" com corpo_html usando {{ nome }} e {{ link_descadastro }}.
- get_or_create por chaves naturais (email/nome). Não envia nada (deixa em rascunho).

### Templates (PT-BR)
- campanhas.html: cabeçalho "Marketing por E-mail — Campanhas" + botão "Nova campanha"; tabela (nome, status
  badge, destinatários, enviados/falhas, criada em, ação Ver). Paginação.
- campanha_form.html: formulário (classe formulario) de criação (assunto, corpos, configuração, lista).
  Nota com os marcadores disponíveis: {{ nome }}, {{ email }}, {{ empresa }}, {{ link_descadastro }}.
- campanha_detalhe.html: dados da campanha, contadores (score-chip/barras), nº de destinatários atuais,
  form POST "Enviar campanha" (com data-confirmar), amostra dos últimos EnvioEmail (tabela), status.
- configuracoes.html: lista de remetentes/configs (sem segredos) + formulário de nova config; por config, um
  pequeno form POST "Enviar teste" (campo e-mail + data-confirmar opcional). Explique o tipo CONSOLE (teste no log).
- contatos.html: tabela paginada de contatos (email, nome, empresa, inscrito) + textarea de importação em massa;
  link para Listas.
- listas.html: lista de listas + formulário de nova lista (multiseleção de contatos).
- descadastrar.html: STANDALONE (copie a estrutura de contas/login.html: tema escuro, carrega css/dashboard.css),
  mostra o e-mail e um botão/form POST "Confirmar descadastro"; após POST, mensagem de sucesso. Textos em PT-BR.
- static/email_marketing/email_marketing.css: pequenos ajustes usando variáveis globais.
- static/email_marketing/email_marketing.js: listener `form[data-confirmar]` (igual ao monitoramento.js) e,
  opcional, mostrar/ocultar campos SMTP conforme o `tipo` (SMTP x Console). Sem CDN; degrada sem JS.

## Checklist final
- [ ] Solução AUTOCONTIDA: remetente + SMTP no próprio módulo; envio via get_connection do módulo (não usa EMAIL_* globais).
- [ ] Senha SMTP cifrada (Fernet), nunca em log/admin/JSON; em branco ao editar = manter.
- [ ] Corpo renderizado por str.replace (SEM motor de template -> sem SSTI); valores do contato escapados no HTML.
- [ ] Envio resiliente por destinatário; log EnvioEmail; contadores/status corretos; conexão fechada no finally.
- [ ] Descadastro PÚBLICO tokenizado (GET confirma, POST efetiva, CSRF), sem login, sem enumeração; página standalone.
- [ ] Todas as demais views admin; POST com CSRF; auditoria objeto_repr[:255]; sem onsubmit inline (use data-confirmar).
- [ ] related_name únicos (config_envio_email, campanhas_email); migrações só __init__.py; seed idempotente e sem rede.
- [ ] Tudo em PT-BR (identificadores de domínio, textos da UI, e-mails de exemplo, docstrings).

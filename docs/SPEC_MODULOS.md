# SPEC ADENDO — Módulos Kanban e SLA (NÃO divergir)

Complementa `docs/SPEC.md`. Vale tudo da SPEC original (nomes, segurança seção 9,
PT-BR, logging, docstrings, `from __future__ import annotations`).

Os dois módulos devem "plugar" no núcleo EXATAMENTE como `apps.prospeccao`.
ANTES de escrever, LEIA estes arquivos de referência e IMITE seus padrões:
- `docs/SPEC.md`
- `apps/nucleo/modulos.py`  (contrato ModuloBase: slug/nome/icone/ordem, itens_menu, contexto_dashboard, cards_resumo)
- `apps/prospeccao/apps.py` (ready() importa o modulo.py)
- `apps/prospeccao/modulo.py` (itens_menu, contexto_dashboard, cards_resumo, _url_ou_hash, _rota_atual)
- `apps/prospeccao/models.py` (estilo de models, TextChoices PT-BR)
- `apps/prospeccao/views.py` (AdminRequeridoMixin nas CBV, @admin_requerido + @csrf_protect + @require_POST nas FBV, auditoria via apps.nucleo.models.RegistroAuditoria com campo **objeto_repr**)
- `apps/prospeccao/urls.py`, `apps/prospeccao/admin.py`, `apps/prospeccao/forms.py`
- `apps/prospeccao/management/commands/seed_prospeccao.py` (comando de seed)
- `templates/base.html` (blocos: titulo, subtitulo, acoes_topo, conteudo, css_extra, js_extra)
- `templates/nucleo/dashboard.html`, `templates/prospeccao/lista.html`, `templates/prospeccao/detalhe.html`
- `static/css/dashboard.css` (REUTILIZE as classes: cartao, cartao__cabecalho, cartao__titulo,
  grade grade--tres/dois-um, badge/badge--roxo/vermelho/amarelo/azul/verde, botao/botao--primario/suave/pequeno/bloco,
  barra/barra__preenchida, avatar/avatar--grande, tag-status--*, filtros, paginacao, formulario, campo,
  lista-dados, mensagens, pilula-periodo, cartoes-resumo, cartao-stat)

## Regras comuns aos dois módulos

1. Segurança: TODAS as views exigem admin. CBV -> `apps.contas.mixins.AdminRequeridoMixin`
   (como 1ª base, antes da view genérica). FBV -> `@apps.contas.decorators.admin_requerido`
   e, se aceitar POST, `@csrf_protect` + `@require_http_methods`/`@require_POST`.
   O `SomenteAdminMiddleware` já protege tudo; isto é defesa em profundidade.
2. Auditoria: nas ações que criam/alteram dados, registre via
   `apps.nucleo.models.RegistroAuditoria.objects.create(usuario=..., acao="...", objeto_repr="...", ip=...)`
   dentro de try/except (best-effort, import tardio). IP = `request.META.get("REMOTE_ADDR")` (não confiar em proxy).
3. ORM sempre. Autoescape mantido. Nada de segredos. `messages` com `fail_silently=True`.
4. Registro no núcleo: `apps.<mod>.apps.<Mod>Config.ready()` faz `from apps.<mod> import modulo`
   dentro de try/except (não impedir o boot). AppConfig.name = "apps.<mod>",
   default_auto_field = "django.db.models.BigAutoField".
5. Migrações: crie SOMENTE `migrations/__init__.py` (vazio). Serão geradas por makemigrations.
6. Cada módulo tem seu CSS próprio em `static/<mod>/<mod>.css`, carregado via
   `{% block css_extra %}<link rel="stylesheet" href="{% static '<mod>/<mod>.css' %}">{% endblock %}`.
   O CSS do módulo USA as variáveis globais (--roxo, --superficie, --borda, --raio, etc.) e só
   acrescenta o que o layout base não tem (colunas do kanban, linha do tempo do SLA…). NÃO redefinir tokens.
7. Todas as páginas estendem `base.html`, definem `{% block titulo %}` e `{% block subtitulo %}`,
   e usam `{% load static nucleo_extras %}`.
8. Contribuição ao dashboard: implemente `cards_resumo(request)` (faixa de KPIs, formato abaixo).
   `contexto_dashboard` pode retornar `{}` (o painel principal é da prospecção).

Formato de card de `cards_resumo` (chaves EXATAS):
```python
{"rotulo": str, "valor": int|str, "detalhe": str, "icone": str, "cor": "#hex", "url": str}
```
Ícones disponíveis (em `templates/parciais/_icones.html`): dashboard, prospeccao, conexoes, buscas,
relatorios, perfil, config, sair, empresa, alerta, sino, email, calendario, ajuda, raio, externo,
menu, kanban, coluna, sla, relogio, tarefa, mais, bandeira, usuario-mais. (Chave desconhecida cai no genérico.)

`itens_menu(request)`: liste os itens do módulo com `{"rotulo","url","icone","ativo"}`,
marcando `ativo` quando `request.resolver_match.view_name` pertencer às rotas do item
(veja o padrão em `apps/prospeccao/modulo.py`). Use `reverse()` com try/except (`_url_ou_hash`).

=================================================================================
## MÓDULO 1 — KANBAN  (app: apps.kanban, namespace de URL: "kanban", ícone: "kanban", ordem=20)
=================================================================================

Arquivos a criar (SOMENTE estes):
- apps/kanban/__init__.py
- apps/kanban/apps.py           (KanbanConfig, ready() importa modulo)
- apps/kanban/models.py
- apps/kanban/modulo.py         (ModuloKanban)
- apps/kanban/forms.py
- apps/kanban/views.py
- apps/kanban/urls.py
- apps/kanban/admin.py
- apps/kanban/migrations/__init__.py
- apps/kanban/management/__init__.py
- apps/kanban/management/commands/__init__.py
- apps/kanban/management/commands/seed_kanban.py
- templates/kanban/lista.html
- templates/kanban/quadro.html
- templates/kanban/novo_quadro.html
- static/kanban/kanban.css
- static/kanban/kanban.js

Modelos (models.py):
- `Quadro`: nome(CharField 120), descricao(TextField blank), arquivado(Bool default False),
  criado_por(FK AUTH_USER_MODEL SET_NULL null), criado_em(auto_now_add), atualizado_em(auto_now).
  Meta ordering ("-criado_em",). __str__ = nome.
- `Coluna`: quadro(FK Quadro CASCADE related_name="colunas"), nome(CharField 80),
  ordem(PositiveIntegerField default 0), limite_wip(PositiveIntegerField null blank),
  cor(CharField 7 default "#7c5cff"). Meta ordering ("quadro","ordem","id").
  Método `em_wip(self)`: qtd de cartões (self.cartoes.count()); property `estourou_wip`.
- `Cartao`: coluna(FK Coluna CASCADE related_name="cartoes"), titulo(CharField 160),
  descricao(TextField blank), ordem(PositiveIntegerField default 0),
  prioridade(TextChoices BAIXA/MEDIA/ALTA/URGENTE, rótulos PT-BR, default MEDIA),
  responsavel(FK AUTH_USER_MODEL SET_NULL null blank related_name="cartoes_kanban"),
  prazo(DateField null blank), concluido(Bool default False),
  criado_por(FK ... SET_NULL null), criado_em(auto_now_add), atualizado_em(auto_now).
  Meta ordering ("coluna","ordem","id").
  Métodos: `cor_prioridade(self)` -> hex por prioridade
  (baixa=#34d399, media=#38bdf8, alta=#fbbf24, urgente=#f87171);
  `classe_badge(self)` -> "badge--verde/azul/amarelo/vermelho" correspondente;
  `atrasado(self)` -> bool (prazo < hoje e não concluido); `iniciais_responsavel(self)`.

modulo.py (ModuloKanban):
- slug="kanban", nome="Kanban", icone="kanban", ordem=20, descricao curta.
- url_inicial -> "kanban:lista".
- itens_menu: um item "Kanban" (icone "kanban", rotas ativas {kanban:lista, kanban:quadro, kanban:novo_quadro}).
- cards_resumo: 3 cards a partir do banco (try/except -> []):
  {"Quadros": Quadro.objects.filter(arquivado=False).count(), icone "kanban", cor "#7c5cff", url kanban:lista},
  {"Tarefas em andamento": Cartao.objects.filter(concluido=False).count(), icone "tarefa", cor "#38bdf8", url kanban:lista},
  {"Tarefas atrasadas": nº de cartões com prazo<hoje e não concluído, icone "alerta", cor "#f87171", url kanban:lista, detalhe "prazo vencido"}.
- contexto_dashboard -> {}.

urls.py (app_name="kanban"), names EXATOS:
- "" -> kanban:lista (QuadroListView; lista de quadros)   [rota: quadros/? use "" na raiz do include -> path("", ...)]
  Use estas rotas:
  - path("", views.QuadroListView.as_view(), name="lista")
  - path("novo/", views.novo_quadro, name="novo_quadro")
  - path("<int:pk>/", views.QuadroDetailView.as_view(), name="quadro")
  - path("<int:pk>/colunas/nova/", views.nova_coluna, name="nova_coluna")   (POST)
  - path("colunas/<int:pk>/cartoes/novo/", views.novo_cartao, name="novo_cartao")  (POST)
  - path("cartoes/<int:pk>/mover/", views.mover_cartao, name="mover_cartao")  (POST)
  - path("cartoes/<int:pk>/concluir/", views.alternar_concluido, name="concluir_cartao")  (POST)

views.py:
- QuadroListView(AdminRequeridoMixin, ListView): quadros não arquivados; template kanban/lista.html; context "quadros".
- QuadroDetailView(AdminRequeridoMixin, DetailView): um Quadro; prefetch colunas e cartões (Prefetch com
  select_related("responsavel")); template kanban/quadro.html; passa colunas ordenadas com seus cartões.
- novo_quadro (FBV, GET/POST): cria Quadro (QuadroForm), criado_por=request.user; redireciona kanban:quadro do novo.
- nova_coluna (POST): cria Coluna no quadro (pk), ordem = última+1.
- novo_cartao (POST): cria Cartão na coluna (pk), ordem = última+1; criado_por=request.user.
- mover_cartao (POST): recebe "coluna_destino" (id) e opcional "ordem"; valida que a coluna destino
  existe e pertence a um Quadro; atualiza coluna e ordem; retorna JsonResponse({"ok": True}) se
  requisição AJAX (cabeçalho X-Requested-With) ou redireciona ao quadro caso contrário.
  Segurança: valide os ids com get_object_or_404; nunca confie em ids arbitrários sem checar existência.
- alternar_concluido (POST): inverte cartao.concluido; retorna JsonResponse ou redireciona.
- Auditoria em criar/mover/concluir.

forms.py: QuadroForm (nome, descricao), ColunaForm (nome, limite_wip, cor), CartaoForm
(titulo, descricao, prioridade, responsavel, prazo — usar widget DateInput type="date").
Validação de tamanho/obrigatoriedade padrão do ModelForm.

admin.py: registrar Quadro, Coluna (inline em Quadro opcional), Cartao com list_display úteis.

seed_kanban.py: cria 1 quadro "Comercial" com colunas [Backlog, Em andamento, Revisão, Concluído]
e ~8 cartões distribuídos, com prioridades variadas, alguns com prazo (inclusive 1 atrasado) e
responsável = primeiro superuser existente (ou None). NÃO faz chamadas externas. Idempotente:
se já existir quadro com esse nome, não duplica (get_or_create).

templates:
- kanban/lista.html: grade de cards (classe cartao) — cada quadro com nome, descrição, contadores
  (nº colunas, nº cartões, nº atrasados como badge), botão "Abrir" (botao--suave) -> kanban:quadro.
  Cabeçalho de página: titulo "Kanban", subtitulo curto; acoes_topo com botão "Novo quadro" (botao--primario)
  -> kanban:novo_quadro. Estado vazio amigável.
- kanban/quadro.html: o QUADRO. titulo = nome do quadro. Um "board" com colunas lado a lado, rolagem
  horizontal (classe própria .kanban-board). Cada coluna (.kanban-coluna) tem cabeçalho (nome + contador +
  badge WIP se estourou) e a lista de cartões (.kanban-cartao) com: título, badge de prioridade
  (use classe_badge/cor), responsável (avatar com iniciais), prazo (com destaque vermelho se atrasado),
  e botões de ação (concluir, e mover ◀ ▶ como fallback sem JS via forms POST com csrf).
  Form "add cartão" ao pé de cada coluna (POST kanban:novo_cartao). Botão "add coluna" (POST kanban:nova_coluna,
  ou um pequeno form). Drag-and-drop opcional via kanban.js (HTML5 drag events -> fetch POST kanban:mover_cartao
  com header X-CSRFToken lido do cookie e X-Requested-With). SEM libs externas.
- kanban/novo_quadro.html: formulário (classe formulario) para criar quadro.
- static/kanban/kanban.css: estilos do board/coluna/cartão usando as variáveis globais.
- static/kanban/kanban.js: drag-and-drop acessível e opcional; degrada sem JS (os botões ◀ ▶ e concluir
  já funcionam via POST). Ler CSRF do cookie "csrftoken".

=================================================================================
## MÓDULO 2 — SLA  (app: apps.sla, namespace: "sla", ícone: "sla", ordem=30)
=================================================================================

Arquivos a criar (SOMENTE estes):
- apps/sla/__init__.py
- apps/sla/apps.py            (SlaConfig, ready() importa modulo)
- apps/sla/models.py
- apps/sla/modulo.py          (ModuloSLA)
- apps/sla/forms.py
- apps/sla/views.py
- apps/sla/urls.py
- apps/sla/admin.py
- apps/sla/migrations/__init__.py
- apps/sla/management/__init__.py
- apps/sla/management/commands/__init__.py
- apps/sla/management/commands/seed_sla.py
- templates/sla/lista.html
- templates/sla/detalhe.html
- templates/sla/politicas.html
- templates/sla/novo_chamado.html
- static/sla/sla.css

Modelos (models.py):
- `Politica`: nome(CharField 120), descricao(TextField blank),
  prazo_resposta_horas(PositiveIntegerField default 4),
  prazo_resolucao_horas(PositiveIntegerField default 24), ativo(Bool default True),
  criado_em(auto_now_add). Meta ordering ("nome",). __str__ = nome.
- `Chamado`: titulo(CharField 160), descricao(TextField blank),
  politica(FK Politica PROTECT related_name="chamados"),
  prioridade(TextChoices BAIXA/MEDIA/ALTA/URGENTE PT-BR default MEDIA),
  status(TextChoices ABERTO/EM_ANDAMENTO/PAUSADO/RESOLVIDO/FECHADO PT-BR default ABERTO),
  solicitante(CharField 150 blank), responsavel(FK AUTH_USER_MODEL SET_NULL null blank related_name="chamados_sla"),
  aberto_em(DateTimeField default timezone.now), primeira_resposta_em(DateTimeField null blank),
  resolvido_em(DateTimeField null blank),
  prazo_resposta(DateTimeField null blank), prazo_resolucao(DateTimeField null blank),
  criado_por(FK ... SET_NULL null), criado_em(auto_now_add), atualizado_em(auto_now).
  Meta ordering ("-aberto_em",).
  save(): se prazo_resposta/prazo_resolucao vazios e houver politica+aberto_em, calcula
    prazo_resposta = aberto_em + timedelta(hours=politica.prazo_resposta_horas) e idem resolução.
  Métodos (todos resilientes a None):
    - `situacao_resolucao(self)` -> "dentro" | "em_risco" | "estourado" | "cumprido".
      Regra: se resolvido_em: "cumprido" se resolvido_em <= prazo_resolucao senão "estourado".
      Senão (aberto): agora > prazo_resolucao -> "estourado"; faltando <25% do tempo -> "em_risco"; senão "dentro".
    - `situacao_resposta(self)` análogo com primeira_resposta_em/prazo_resposta.
    - `percentual_resolucao(self)` -> int 0..100 (tempo consumido do prazo de resolução).
    - `tempo_restante_texto(self)` -> ex.: "faltam 3 h", "atrasado 2 h", "—".
    - `classe_situacao(self, situacao)` -> "tag-status--concluida/erro/pendente/nova" p/ badges
      (mapa: dentro->tag-status--nova, em_risco->tag-status--pendente, estourado->tag-status--erro,
       cumprido->tag-status--qualificada). Reutilize as classes tag-status existentes.

modulo.py (ModuloSLA):
- slug="sla", nome="SLA", icone="sla", ordem=30.
- url_inicial -> "sla:lista".
- itens_menu: "Chamados" (icone "sla", rotas ativas {sla:lista, sla:detalhe, sla:novo_chamado}),
  "Políticas" (icone "config", rota {sla:politicas}).
- cards_resumo (try/except -> []): calcular em Python iterando um queryset enxuto (evite N+1
  com select_related("politica")). 4 cards:
  {"Chamados abertos": nº status in (ABERTO, EM_ANDAMENTO, PAUSADO), icone "sla", cor "#7c5cff", url sla:lista},
  {"SLA em risco": nº abertos com situacao_resolucao()=="em_risco", icone "alerta", cor "#fbbf24", url sla:lista},
  {"SLA estourado": nº com situacao_resolucao()=="estourado", icone "alerta", cor "#f87171", url sla:lista},
  {"No prazo": percentual de cumpridos dentro do prazo entre resolvidos (ex.: "92%"), icone "tarefa", cor "#34d399", url sla:lista, detalhe "cumprimento"}.
- contexto_dashboard -> {}.

urls.py (app_name="sla"):
- path("", views.ChamadoListView.as_view(), name="lista")
- path("novo/", views.novo_chamado, name="novo_chamado")
- path("politicas/", views.politicas, name="politicas")
- path("<int:pk>/", views.ChamadoDetailView.as_view(), name="detalhe")
- path("<int:pk>/responder/", views.registrar_resposta, name="registrar_resposta")  (POST)
- path("<int:pk>/resolver/", views.resolver, name="resolver")  (POST)

views.py:
- ChamadoListView(AdminRequeridoMixin, ListView): paginate_by=20, select_related("politica","responsavel");
  filtros por status (querystring "status") e por situação ("situacao": em_risco/estourado) aplicados
  em Python quando forem de SLA (ou em query quando possível). template sla/lista.html; exponha opcoes de filtro.
- ChamadoDetailView(AdminRequeridoMixin, DetailView): template sla/detalhe.html; passa as situações,
  percentuais e textos calculados.
- novo_chamado (FBV GET/POST): ChamadoForm; criado_por=request.user; salva (save calcula prazos); auditoria.
- politicas (FBV GET/POST): lista + cria Politica (PoliticaForm).
- registrar_resposta (POST): set primeira_resposta_em = timezone.now() se vazio; status EM_ANDAMENTO; auditoria.
- resolver (POST): set resolvido_em = timezone.now(); status RESOLVIDO; auditoria.

forms.py: ChamadoForm (titulo, descricao, politica, prioridade, solicitante, responsavel — prazos NÃO no form,
são calculados), PoliticaForm (nome, descricao, prazo_resposta_horas, prazo_resolucao_horas, ativo).

admin.py: Politica e Chamado com list_display (status, prioridade, prazos, responsável).

seed_sla.py: cria 2 políticas (ex.: "Padrão" 4h/24h e "Premium" 1h/8h) e ~8 chamados cobrindo
todos os estados: dentro do prazo, em risco (aberto_em recuado para faltar <25%), estourado
(aberto_em bem no passado, sem resolver), cumprido no prazo (resolvido_em <= prazo) e um estourado resolvido.
Ajuste aberto_em com timezone.now() - timedelta(...) para produzir cada situação. Idempotente (get_or_create
por título). Responsável = primeiro superuser (ou None). SEM chamadas externas.

templates:
- sla/lista.html: cabeçalho "SLA — Chamados", subtitulo; acoes_topo "Novo chamado" (botao--primario).
  Filtros (classe filtros) por status/situação. Tabela (classe tabela) com colunas: Chamado (título + solicitante),
  Política, Prioridade (badge), Status (tag-status--*), Situação do SLA (badge via classe_situacao),
  Prazo/restante (tempo_restante_texto), Responsável (avatar). Link ao detalhe. Paginação (classe paginacao).
- sla/detalhe.html: ficha do chamado com barra de progresso (classe barra/barra__preenchida) do
  percentual_resolucao, badges de situação, linha do tempo (aberto/1ª resposta/resolvido), e formulários
  POST "Registrar resposta" e "Resolver" (csrf), além dos dados (lista-dados).
- sla/politicas.html: lista de políticas (cards ou tabela) + formulário de nova política (formulario).
- sla/novo_chamado.html: formulário de novo chamado.
- static/sla/sla.css: barras/medidores/linha do tempo extras usando variáveis globais.

## Checklist final de cada agente
- [ ] ready() registra o módulo; slug/ordem/ícone corretos.
- [ ] Todas as views exigem admin (mixin/decorator) e POST tem csrf.
- [ ] cards_resumo no formato exato; itens_menu com "ativo" correto.
- [ ] Templates estendem base.html, carregam css_extra do módulo, reutilizam classes do design system.
- [ ] Somente os arquivos listados; migrations só __init__.py; seed idempotente e sem rede.
- [ ] PT-BR, docstrings, logging, sem segredos, sem N+1 evidente.

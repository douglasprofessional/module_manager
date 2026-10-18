# SPEC ADENDO 2 — Módulos Monitoramento (VPS) e Backup (NÃO divergir)

Complementa `docs/SPEC.md` e `docs/SPEC_MODULOS.md`. Vale TUDO deles (nomes, segurança seção 9,
PT-BR, logging, docstrings, `from __future__ import annotations`, only-admin, CSRF em POST).

ANTES de escrever, LEIA e IMITE os padrões já aprovados:
- `apps/nucleo/modulos.py` (ModuloBase: slug/nome/icone/ordem, itens_menu, contexto_dashboard, cards_resumo)
- `apps/nucleo/criptografia.py` (`criptografar`/`descriptografar` — Fernet; USE para todo segredo em repouso)
- `apps/prospeccao/{apps,modulo,models,views,urls,forms,admin}.py` e `.../management/commands/seed_prospeccao.py`
- `apps/prospeccao/models.py::ConexaoGoogle` (padrão de campo cifrado: `*_criptografada` + property que decifra/cifra)
- `apps/kanban/views.py` (auditoria via `RegistroAuditoria(..., objeto_repr=(x or "")[:255], ...)`; JSON em AJAX)
- `templates/base.html` (blocos: titulo, subtitulo, acoes_topo, conteudo, css_extra, js_extra)
- `templates/parciais/_icones.html`, `static/css/dashboard.css` (design system: cartao, grade--tres/dois-um,
  badge--*, botao--*, barra/barra__preenchida, tag-status--*, avatar, filtros, paginacao, formulario, lista-dados,
  cartoes-resumo/cartao-stat, score-chip, pastilha--sim/nao/neutro)

Regras comuns (idênticas ao adendo 1):
- Registro: `apps.<mod>.apps.<Mod>Config.ready()` faz `from apps.<mod> import modulo` em try/except; name="apps.<mod>",
  default_auto_field="django.db.models.BigAutoField".
- Migrações: só `migrations/__init__.py` vazio.
- CSS próprio em `static/<mod>/<mod>.css` (usa variáveis globais; não redefine tokens), carregado por css_extra.
- `cards_resumo(request)` no formato EXATO: `{"rotulo","valor","detalhe","icone","cor":"#hex","url"}`. `contexto_dashboard -> {}`.
- `related_name` ÚNICO por modelo alvo. Já em uso no Usuario: registros_auditoria, conexoes_google, buscas,
  quadros_kanban, cartoes_kanban, cartoes_kanban_criados, chamados_sla, chamados_sla_criados. NÃO repita nenhum.
- Auditoria: import tardio de `apps.nucleo.models.RegistroAuditoria`, best-effort, `objeto_repr=(x or "")[:255]`,
  `ip=request.META.get("REMOTE_ADDR")`.
- Ícones já adicionados a `_icones.html` para você: servidor, backup, disco, download, cpu, atualizar, lixeira, editar
  (além dos existentes: alerta, tarefa, config, calendario, mais, externo, relogio, sla, kanban...).

Os apps `apps.monitoramento` e `apps.backup` já estão em INSTALLED_APPS e em config/urls.py (namespaces
`monitoramento` e `backup`). `paramiko` já está em requirements.txt. `settings.BACKUPS_DIR` já existe.

=================================================================================
## MÓDULO 3 — MONITORAMENTO DE VPSs  (app apps.monitoramento, ns "monitoramento", ícone "servidor", ordem 40)
=================================================================================

Objetivo: painel estilo Proxmox para monitorar servidores/VPS onde quer que estejam, via SSH.

Arquivos a criar (SOMENTE estes):
- apps/monitoramento/__init__.py
- apps/monitoramento/apps.py
- apps/monitoramento/models.py
- apps/monitoramento/modulo.py
- apps/monitoramento/forms.py
- apps/monitoramento/views.py
- apps/monitoramento/urls.py
- apps/monitoramento/admin.py
- apps/monitoramento/services/__init__.py
- apps/monitoramento/services/ssh_coletor.py
- apps/monitoramento/migrations/__init__.py
- apps/monitoramento/management/__init__.py
- apps/monitoramento/management/commands/__init__.py
- apps/monitoramento/management/commands/seed_monitoramento.py
- templates/monitoramento/lista.html
- templates/monitoramento/detalhe.html
- templates/monitoramento/form.html
- static/monitoramento/monitoramento.css
- static/monitoramento/monitoramento.js  (opcional; auto-refresh leve por meta/JS sem libs externas)

Modelos (models.py):
- `ServidorVPS`:
  nome(CharField 120), host(CharField 255 — IP ou domínio), porta_ssh(PositiveIntegerField default 22),
  usuario(CharField 64, default "root"),
  metodo_auth(TextChoices: SENHA="senha", CHAVE="chave"; default SENHA),
  senha_criptografada(TextField blank default ""),
  chave_privada_criptografada(TextField blank default ""),
  passphrase_criptografada(TextField blank default ""),
  host_key_fingerprint(CharField 200 blank default "" — SHA-256 da host key, TOFU),
  provedor(CharField 80 blank), tags(CharField 200 blank), observacoes(TextField blank),
  ativo(Bool default True),
  ultimo_status(TextChoices: DESCONHECIDO/ONLINE/OFFLINE/ERRO; default DESCONHECIDO),
  ultima_coleta_em(DateTimeField null blank),
  criado_por(FK AUTH_USER_MODEL SET_NULL null blank related_name="vps_monitoradas"),
  criado_em(auto_now_add), atualizado_em(auto_now).
  SEGREDOS: exponha properties `senha`, `chave_privada`, `passphrase` que decifram sob demanda via
  apps.nucleo.criptografia (getter decifra; setter cifra; string vazia limpa) — MESMO padrão de ConexaoGoogle.chave_api.
  NUNCA exiba os segredos em admin/serialização. Property `tem_credencial` (bool) sem revelar valor.
  Meta ordering ("nome",). __str__ = f"{nome} ({host})".
  Métodos de apresentação: `classe_status()` -> tag-status--* (online->qualificada/verde, offline->erro,
  erro->erro, desconhecido->neutro/pendente); `iniciais()` p/ avatar; `cor_uso(pct)` -> "#hex"
  (verde<70, amarelo 70-89, vermelho>=90) para as barras.
- `LeituraMetrica` (histórico):
  servidor(FK ServidorVPS CASCADE related_name="leituras"),
  coletado_em(auto_now_add, db_index), online(Bool default False),
  cpu_pct(Float null), mem_pct(Float null), mem_total_mb(Integer null), mem_usada_mb(Integer null),
  disco_pct(Float null), disco_total_gb(Float null), disco_usado_gb(Float null),
  uptime_segundos(BigInteger null), carga1(Float null), carga5(Float null), carga15(Float null),
  nucleos(Integer null), sistema(CharField 200 blank — uname), erro(TextField blank).
  Meta ordering ("-coletado_em",).
  Helper `uptime_texto()` -> "Xd Yh" a partir de uptime_segundos.

modulo.py (ModuloMonitoramento): slug="monitoramento", nome="Monitoramento", icone="servidor", ordem=40.
- url_inicial -> "monitoramento:lista".
- itens_menu: item "Servidores" (icone "servidor", rotas ativas {monitoramento:lista, :detalhe, :novo, :editar}).
- cards_resumo (try/except -> []): 3 KPIs a partir do banco:
  {"Servidores": ServidorVPS.objects.filter(ativo=True).count(), icone "servidor", cor "#7c5cff", url lista},
  {"Online": nº com ultimo_status=ONLINE, icone "atualizar", cor "#34d399", url lista, detalhe "ativos agora"},
  {"Offline/Erro": nº com ultimo_status in (OFFLINE, ERRO), icone "alerta", cor "#f87171", url lista}.
- contexto_dashboard -> {}.

Serviço SEGURO (services/ssh_coletor.py) — CRÍTICO:
- `import paramiko` DENTRO da função (lazy). Se ImportError, retornar métrica com erro="paramiko não instalado".
- Função `coletar_metricas(servidor) -> dict` que:
  * decifra credenciais só em memória (nunca loga);
  * conecta com paramiko.SSHClient, timeout de conexão ~10s, auth por senha OU chave (carrega a chave privada
    de string via io.StringIO tentando Ed25519/ECDSA/RSA; usa passphrase se houver);
  * VERIFICAÇÃO DE HOST KEY (anti-MITM): use uma MissingHostKeyPolicy customizada OU verifique manualmente:
    após conectar (ou via Transport), obtenha a host key, calcule o fingerprint SHA-256 (base64) e:
      - se servidor.host_key_fingerprint vazio -> TOFU: salve o fingerprint (retorne-o para a view persistir);
      - se preenchido e diferente -> RECUSE (erro "host key mudou — possível MITM"), NÃO colete.
    (Implementação recomendada: policy que rejeita desconhecidas + carregamento do fingerprint conhecido; ou
     conectar e comparar `transport.get_remote_server_key()`. Documente a escolha.)
  * executa UM comando FIXO e read-only (SEM interpolar dados do servidor no texto do comando) que colete:
    /proc/stat (2 amostras com sleep 1 p/ CPU%), /proc/meminfo, df -kP /, /proc/uptime, /proc/loadavg, nproc, uname -sr.
    Ex. de abordagem: enviar um pequeno script sh via exec_command com timeout ~15s que imprime linhas "CHAVE=valor".
  * faz o PARSE em Python de forma tolerante (valores ausentes -> None), calcula cpu_pct/mem_pct/disco_pct;
  * retorna dict com todas as chaves de LeituraMetrica + "fingerprint_novo" (ou None) + "online" + "erro".
- NUNCA usar shell com dados do usuário. host/porta/usuario vão como PARÂMETROS do paramiko.connect (não shell).
- Fechar sempre a conexão (finally). Nenhum segredo em log/exception message.

views.py:
- Todas admin (AdminRequeridoMixin nas CBV; @admin_requerido + @csrf_protect + @require_POST nas ações).
- `ServidorListView`: grid de servidores (ativos e inativos), com a última leitura (Prefetch/anotação) p/ os medidores.
- `ServidorDetailView`: última leitura + histórico (últimas ~30 leituras) p/ um mini-gráfico de linha
  (use a tag `pontos_polyline` do núcleo com a série de cpu_pct/mem_pct). Botão "Coletar agora".
- `novo` (GET/POST): ServidorForm cria servidor; criado_por=request.user; NÃO exige coleta.
- `editar` (GET/POST): edita; permite limpar/rotacionar credenciais e resetar host_key_fingerprint.
- `coletar` (POST): chama ssh_coletor.coletar_metricas(servidor), cria LeituraMetrica, atualiza
  servidor.ultimo_status/ultima_coleta_em e, se veio fingerprint_novo e o campo estava vazio, salva-o (TOFU).
  Responde JSON via AJAX (X-Requested-With) ou redireciona com messages. Auditoria.
- `coletar_todos` (POST): itera os servidores ativos (com um teto, ex.: 50) chamando a coleta; resiliente por servidor.
- `excluir` (POST): remove o servidor (e leituras por cascade). Auditoria.

forms.py: `ServidorForm` (ModelForm) com campos: nome, host, porta_ssh, usuario, metodo_auth, provedor, tags,
observacoes, ativo + campos EXTRA de senha/chave/passphrase como widgets de escrita (PasswordInput / Textarea)
que, no save, são cifrados nas properties (senha/chave_privada/passphrase). Ao editar, os campos de segredo ficam
VAZIOS e só sobrescrevem se preenchidos (não apagar credencial existente ao editar sem digitar de novo).
Validação: porta 1..65535; host obrigatório; se metodo_auth=chave exigir chave (na criação).

urls.py (app_name="monitoramento"): names EXATOS:
- "" -> lista ; "novo/" -> novo ; "<int:pk>/" -> detalhe ; "<int:pk>/editar/" -> editar ;
- "<int:pk>/coletar/" -> coletar (POST) ; "coletar-todos/" -> coletar_todos (POST) ; "<int:pk>/excluir/" -> excluir (POST).

admin.py: ServidorVPS (list_display: nome, host, usuario, ultimo_status, ultima_coleta_em; NUNCA campos de segredo;
readonly nos *_criptografada ou exclua-os) e LeituraMetrica (readonly, list_display de métricas).

seed_monitoramento.py: cria ~4 servidores demo (sem credenciais reais/sem SSH) e, para cada, ~20 LeituraMetrica
históricas com valores plausíveis (variando CPU/RAM/disco), definindo ultimo_status e ultima_coleta_em coerentes
(1 offline, 1 com disco crítico >90%). Idempotente (get_or_create por nome). NÃO faz rede/SSH.
Espalhe coletado_em via update() (auto_now_add) para o gráfico.

templates:
- lista.html: cabeçalho "Monitoramento" + botão "Novo servidor" (acoes_topo) + "Coletar todos" (form POST).
  Grid de cartões (classe cartao) por servidor: nome+host, badge tag-status--* do status, barras (classe barra)
  de CPU/RAM/disco com cor por uso, uptime, última coleta, botões Detalhes/Coletar/Editar. Estado vazio amigável.
- detalhe.html: métricas atuais (score-chip/barras), mini-gráfico de linha (pontos_polyline) do histórico,
  tabela das últimas leituras, dados de conexão (SEM segredos — só host/porta/usuário/método), botões Coletar/Editar/Excluir (POST).
- form.html: formulário de criação/edição (classe formulario). Deixe claro que segredos em branco = manter.
- monitoramento.css: medidores/gauges e grid, usando variáveis globais. monitoramento.js opcional (auto-refresh e
  POST de "coletar" via fetch com CSRF do cookie csrftoken; degrada sem JS pelos forms).

=================================================================================
## MÓDULO 4 — BACKUP  (app apps.backup, ns "backup", ícone "backup", ordem 50)
=================================================================================

Objetivo: gerar backups (1) por módulo (dados do app correspondente) e (2) completo (todos os dados + banco + mídia).
O projeto usa UM banco compartilhado; "backup do módulo" = os dados do app daquele módulo (fixtures Django,
restauráveis com loaddata). O "completo" inclui o banco inteiro e conteúdos.

Arquivos a criar (SOMENTE estes):
- apps/backup/__init__.py
- apps/backup/apps.py
- apps/backup/models.py
- apps/backup/modulo.py
- apps/backup/forms.py
- apps/backup/views.py
- apps/backup/urls.py
- apps/backup/admin.py
- apps/backup/services/__init__.py
- apps/backup/services/backup_service.py
- apps/backup/migrations/__init__.py
- templates/backup/lista.html
- templates/backup/novo.html
- static/backup/backup.css

Modelo (models.py):
- `Backup`:
  tipo(TextChoices: MODULO="modulo", COMPLETO="completo"),
  escopo(CharField 100 — app_label do módulo, ou "completo"),
  rotulo(CharField 160 — descrição amigável, ex.: "Kanban" ou "Estrutura completa"),
  arquivo(CharField 255 — nome do arquivo relativo dentro de BACKUPS_DIR; NÃO caminho absoluto do usuário),
  tamanho_bytes(BigInteger default 0), checksum_sha256(CharField 64 blank),
  incluir_media(Bool default False),
  status(TextChoices: PENDENTE/EXECUTANDO/CONCLUIDO/ERRO; default PENDENTE),
  mensagem(TextField blank), criado_por(FK AUTH_USER_MODEL SET_NULL null blank related_name="backups_gerados"),
  criado_em(auto_now_add), concluido_em(DateTimeField null blank).
  Meta ordering ("-criado_em",).
  Métodos: `tamanho_texto()` -> humaniza bytes (KB/MB/GB); `classe_status()` -> tag-status--*;
  `caminho_absoluto()` -> Path(settings.BACKUPS_DIR)/arquivo (uso interno); `existe()` -> bool.

modulo.py (ModuloBackup): slug="backup", nome="Backup", icone="backup", ordem=50.
- url_inicial -> "backup:lista".
- itens_menu: item "Backup" (icone "backup", rotas {backup:lista, backup:novo}).
- cards_resumo (try/except -> []): 2 KPIs:
  {"Backups": Backup.objects.filter(status=CONCLUIDO).count(), icone "backup", cor "#7c5cff", url lista},
  {"Último": rótulo/tempo do backup concluído mais recente (ou "—"), icone "atualizar", cor "#34d399", url lista}.
- contexto_dashboard -> {}.

Serviço SEGURO (services/backup_service.py) — CRÍTICO:
- Diretório de saída = `settings.BACKUPS_DIR` (Path). Crie-o com `mkdir(parents=True, exist_ok=True)`.
- `modulos_disponiveis() -> list[tuple[app_label, rotulo]]`: a partir de `apps.nucleo.modulos.registro.todos()`
  (slug == app_label de cada módulo) MAIS os apps de núcleo ("contas","nucleo") rotulados "Núcleo (contas/usuários e auditoria)".
  Esta é a ALLOWLIST — nenhuma outra app pode ser exportada.
- `backup_modulo(app_label, criado_por) -> Backup`:
  * valida app_label contra a allowlist (senão levanta ValueError);
  * gera nome de arquivo SEGURO: f"modulo_{app_label}_{timestamp}.json.gz" (timestamp sem espaços/':'; use um
    contador/uuid curto se necessário — NÃO use entrada do usuário no nome);
  * roda `django.core.management.call_command('dumpdata', app_label, format='json', indent=2,
    use_natural_foreign_keys=True, use_natural_primary_keys=True, stdout=<gzip text stream>)` gravando
    direto num `gzip.open(caminho, 'wt', encoding='utf-8')`;
  * calcula tamanho e checksum sha256; cria/atualiza o registro Backup com status CONCLUIDO (ou ERRO em exceção).
- `backup_completo(incluir_media, criado_por) -> Backup`:
  * cria um .zip f"completo_{timestamp}.zip" contendo:
      - "dados/dados_completos.json.gz": dumpdata de TODAS as apps do projeto (exclua contenttypes e auth.permission
        para restauração limpa; inclua as apps do projeto) — gzip;
      - "banco/<dump>": dump nativo do banco quando possível:
          * sqlite: use a API `sqlite3.connect(orig).backup(dest)` para "banco/db.sqlite3";
          * postgres: `pg_dump` via subprocess FORMA-LISTA (sem shell=True), host/porta/db/usuário vindos de
            settings.DATABASES['default'], senha via env PGPASSWORD; se o binário não existir (FileNotFoundError),
            registre aviso na mensagem e siga só com o dumpdata. NUNCA interpole credenciais no shell.
      - se incluir_media e settings.MEDIA_ROOT existir: adicione a árvore de MEDIA_ROOT sob "media/".
  * checksum/tamanho; registro Backup CONCLUIDO/ERRO com mensagem detalhando o que foi incluído.
- Nada de shell=True. Nenhum segredo em log. Tolerante a falhas por etapa (registra na mensagem).

views.py:
- Todas admin. `BackupListView` (ListView, paginação): lista os backups com status/tamanho/ações (Baixar/Excluir).
- `novo` (GET/POST): form escolhe tipo (modulo/completo), escopo (select das modulos_disponiveis quando modulo),
  incluir_media (checkbox, só p/ completo). No POST (csrf), executa SINCRONAMENTE o serviço correspondente e
  redireciona à lista com messages. Auditoria.
- `baixar` (GET, admin): `get_object_or_404(Backup, pk=...)`; obtém caminho = backup.caminho_absoluto();
  VALIDE que o caminho resolvido está DENTRO de settings.BACKUPS_DIR (use Path.resolve() + `is_relative_to` /
  os.path.commonpath) — anti path traversal; se não existir -> 404. Responda `FileResponse(open(path,'rb'),
  as_attachment=True, filename=<nome seguro>)`. NÃO exponha caminho no cliente.
- `excluir` (POST, admin): apaga o arquivo (só se dentro de BACKUPS_DIR) e o registro. Auditoria.
- NÃO implemente restauração pela UI (perigosa); a restauração é via CLI (loaddata) — documentada no README.

forms.py: `BackupForm` com tipo (ChoiceField), escopo (ChoiceField populado com modulos_disponiveis()),
incluir_media (BooleanField). Validação: se tipo=modulo, escopo deve estar na allowlist.

urls.py (app_name="backup"): "" -> lista ; "novo/" -> novo ; "<int:pk>/baixar/" -> baixar ;
"<int:pk>/excluir/" -> excluir (POST).

admin.py: Backup (readonly em arquivo/checksum/tamanho; list_display: criado_em, tipo, escopo, status, tamanho).

templates:
- lista.html: cabeçalho "Backup" + botão "Novo backup" (acoes_topo). Tabela: Quando, Tipo (badge), Escopo,
  Tamanho, Status (tag-status--*), Ações (Baixar [se concluído], Excluir [POST]). Explique em nota que o backup
  por módulo é um fixture (loaddata) e o completo inclui o banco.
- novo.html: formulário (classe formulario) com tipo/escopo/incluir_media; JS mínimo opcional para mostrar/ocultar
  o select de escopo conforme o tipo (degrada sem JS — o backend valida). 
- backup.css: pequenos ajustes usando variáveis globais.

## Checklist final (cada agente)
- [ ] ready() registra; slug/ordem/ícone corretos; related_name únicos.
- [ ] Segredos SEMPRE cifrados (Fernet) e nunca em log/admin/JSON. (Monitoramento)
- [ ] SSH: host key verificada (TOFU + rejeição em mudança); comando FIXO read-only; sem shell com dados do usuário. (Monitoramento)
- [ ] Backup: diretório privado; download só admin via FileResponse com validação anti path traversal; allowlist de apps;
      sem shell=True; pg_dump em forma-lista. (Backup)
- [ ] Todas as views admin; POST com CSRF; auditoria com objeto_repr[:255].
- [ ] Templates estendem base.html, css_extra do módulo, reutilizam o design system; todo {% url %} existe; todo
      método chamado no template é zero-arg; {% csrf_token %} em todo form POST; nada de CDN externa.
- [ ] Migrações só __init__.py; seed idempotente e sem rede (Monitoramento).

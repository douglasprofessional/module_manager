"""Textos de conteúdo centralizados (títulos, subtítulos, menus e rótulos).

Este arquivo é a FONTE ÚNICA dos textos exibidos na interface: títulos e
subtítulos de páginas, títulos de cartões/seções, itens de menu, nomes e
descrições dos módulos, KPIs do dashboard e todos os textos do módulo de
Prospecção. Para alterar um texto, edite apenas o valor aqui — todos os
lugares que o exibem passam a mostrar o novo conteúdo.

Organização das chaves (caminho pontuado ``secao.subsecao.chave``):

- ``geral``    — textos globais (nome padrão do sistema, rótulos genéricos).
- ``menu`` / ``topo`` — barra lateral e barra superior.
- ``modulos.<slug>`` — nome, descrição, itens de menu e cards de KPI de cada
  módulo (lidos pelos ``modulo.py``).
- ``<app>.<pagina>`` — títulos e textos de cada página (templates).

Uso nos templates (``{% load nucleo_extras %}``)::

    {% texto "prospeccao.painel.titulo" %}
    {% texto "nucleo.dashboard.boas_vindas_titulo" nome=site_nome %}
    {% texto "prospeccao.lista.titulo" as titulo_lista %}

Uso no Python::

    from apps.nucleo.textos import texto
    texto("modulos.prospeccao.nome")
    texto("prospeccao.nova_busca.msg_executada", total=10)

Variáveis entre chaves (``{nome}``) são preenchidas pelos parâmetros nomeados.
Uma chave inexistente NÃO quebra a página: é registrada no log e o próprio
caminho da chave é exibido (fácil de localizar). Para conferir todas as chaves
usadas no projeto, rode ``python manage.py verificar_textos``.

Regras de manutenção: altere apenas os VALORES; ao renomear/remover uma chave,
atualize os pontos de uso (``verificar_textos`` aponta os que ficarem órfãos).
Não use chaves ``{`` ``}`` literais dentro dos textos (são marcadores).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("modulos.nucleo.textos")


TEXTOS: dict[str, Any] = {
    # ------------------------------------------------------------------
    # Global
    # ------------------------------------------------------------------
    "geral": {
        "nome_padrao": "Gerenciador de Módulos",
        "marca_padrao": "modulos",
        "sem_valor": "—",
        "pular_conteudo": "Pular para o conteúdo",
        "ir_dashboard": "{nome} — ir para o dashboard",
        "voltar_dashboard": "Voltar ao dashboard",
        "sim": "Sim",
        "nao": "Não",
    },
    # ------------------------------------------------------------------
    # Barra lateral e barra superior
    # ------------------------------------------------------------------
    "menu": {
        "aria_principal": "Navegação principal",
        "aria_menu_principal": "Principal",
        "aria_configuracoes": "Configurações gerais",
        "dashboard": "Dashboard",
        "secao_geral": "Configurações Gerais do Sistema",
        "secao_conta": "Conta",
        "meu_perfil": "Meu perfil",
        "configuracoes": "Configurações",
        "sair": "Sair",
        "fechar_menu": "Fechar menu",
        "ajuda_titulo": "Precisa de ajuda?",
        "ajuda_texto": "Consulte a documentação ou fale com o suporte.",
        "ajuda_botao": "Falar com suporte",
    },
    "topo": {
        "abrir_menu": "Abrir menu",
        "configuracoes_aria": "Configurações do sistema",
        "configuracoes_dica": "Configurações",
        "tema_claro_aria": "Mudar para tema claro",
        "tema_claro_dica": "Tema claro",
        "tema_escuro_aria": "Mudar para tema escuro",
        "tema_escuro_dica": "Tema escuro",
        "meu_perfil_aria": "Meu perfil",
        "papel_admin": "Administrador",
        "papel_equipe": "Equipe",
    },
    # ------------------------------------------------------------------
    # Metadados dos módulos (nome, descrição, menu e KPIs do dashboard)
    # ------------------------------------------------------------------
    "modulos": {
        "prospeccao": {
            "nome": "Prospecção",
            "descricao": "Encontra e qualifica empresas com oportunidades digitais.",
            "menu": {
                "painel": "Painel",
                "empresas": "Empresas",
                "conexoes": "Conexões",
                "nova_busca": "Nova busca",
            },
            "cards": {
                "empresas_rotulo": "Empresas",
                "empresas_detalhe": "leads na base",
                "alta_rotulo": "Alta oportunidade",
                "alta_detalhe": "score ≥ 70",
                "qualificadas_rotulo": "Qualificadas",
                "qualificadas_detalhe": "prontas p/ contato",
                "alertas_google_rotulo": "Alertas no Google",
                "alertas_google_detalhe": "perfis com problemas no Places",
            },
            "acoes": {
                "prioritario": "Prioritário",
                "em_breve": "Em breve",
                "contatar": "Contatar {nome}",
                "novo_lead": "Novo lead",
            },
            "destaque": {
                "titulo": "Maior oportunidade",
                "texto": "{nome} tem score de oportunidade {score} ({resumo}).",
                "sem_problemas": "sem problemas evidentes",
            },
        },
        "kanban": {
            "nome": "Kanban",
            "descricao": "Organiza tarefas em quadros com colunas e cartões.",
            "menu": {"kanban": "Kanban"},
            "cards": {
                "quadros_rotulo": "Quadros",
                "quadros_detalhe": "em uso",
                "andamento_rotulo": "Tarefas em andamento",
                "andamento_detalhe": "cartões abertos",
                "atrasadas_rotulo": "Tarefas atrasadas",
                "atrasadas_detalhe": "prazo vencido",
            },
        },
        "sla": {
            "nome": "SLA",
            "descricao": "Acompanha chamados e o cumprimento dos prazos de atendimento.",
            "menu": {"chamados": "Chamados", "politicas": "Políticas"},
            "cards": {
                "abertos_rotulo": "Chamados abertos",
                "abertos_detalhe": "em atendimento",
                "risco_rotulo": "SLA em risco",
                "risco_detalhe": "prazo se aproximando",
                "estourado_rotulo": "SLA estourado",
                "estourado_detalhe": "prazo excedido",
                "no_prazo_rotulo": "No prazo",
                "no_prazo_detalhe": "cumprimento",
            },
        },
        "monitoramento": {
            "nome": "Monitoramento",
            "descricao": "Monitora servidores/VPS por SSH: CPU, memória, disco e uptime.",
            "menu": {"servidores": "Servidores"},
            "cards": {
                "servidores_rotulo": "Servidores",
                "servidores_detalhe": "ativos",
                "online_rotulo": "Online",
                "online_detalhe": "ativos agora",
                "offline_rotulo": "Offline/Erro",
                "offline_detalhe": "requer atenção",
            },
        },
        "backup": {
            "nome": "Backup",
            "descricao": "Gera backups por módulo (fixtures) e backups completos (banco + conteúdos).",
            "menu": {"backup": "Backup"},
            "cards": {
                "backups_rotulo": "Backups",
                "backups_detalhe": "concluídos",
                "ultimo_rotulo": "Último",
                "ultimo_vazio": "nenhum backup ainda",
            },
        },
        "email_marketing": {
            "nome": "Marketing",
            "descricao": (
                "Cadastre o remetente e o SMTP no próprio módulo e envie campanhas em "
                "massa, com contatos, listas e descadastro público."
            ),
            "menu": {
                "campanhas": "Campanhas",
                "modelos": "Modelos de e-mail",
                "contatos": "Contatos",
                "configuracoes": "Configurações de envio",
            },
            "cards": {
                "campanhas_rotulo": "Campanhas enviadas",
                "campanhas_detalhe": "enviadas ou parciais",
                "contatos_rotulo": "Contatos inscritos",
                "contatos_detalhe": "recebem campanhas",
                "emails_rotulo": "E-mails enviados",
                "emails_detalhe": "total",
            },
        },
        "cupons": {
            "nome": "Cupons",
            "descricao": "Gerencia cupons de desconto, clientes e cobrancas mensais.",
            "menu": {"cupons": "Cupons", "clientes": "Clientes", "cobrancas": "Cobrancas"},
            "cards": {
                "cupons_rotulo": "Cupons ativos",
                "cupons_detalhe": "aplicados no mes",
                "clientes_rotulo": "Clientes ativos",
                "clientes_detalhe": "na base",
                "aniversariantes_rotulo": "Aniversariantes",
                "aniversariantes_detalhe": "cupom automatico do mes",
                "cobrancas_rotulo": "Cobrancas em aberto",
                "cobrancas_detalhe": "pendentes ou em atraso",
            },
        },
        "blog": {
            "nome": "Blog",
            "descricao": "Cria e publica conteúdo com validação de SEO, GEO e acessibilidade.",
            "menu": {
                "posts": "Posts",
                "novo_post": "Novo post",
                "categorias": "Categorias",
                "tags": "Tags",
            },
            "cards": {
                "publicados_rotulo": "Publicados",
                "publicados_detalhe": "posts no ar",
                "rascunhos_rotulo": "Rascunhos",
                "rascunhos_detalhe": "em edição",
                "agendados_rotulo": "Agendados",
                "agendados_detalhe": "aguardando publicação",
            },
        },
    },
    # ------------------------------------------------------------------
    # Núcleo
    # ------------------------------------------------------------------
    "nucleo": {
        "dashboard": {
            "titulo": "Dashboard",
            "subtitulo": "Olá {nome}, aqui está a visão geral dos módulos ativos.",
            "gerenciar_modulos": "Gerenciar módulos",
            "boas_vindas_titulo": "Bem-vindo(a) ao {nome}",
            "boas_vindas_texto": (
                "Nenhum módulo está habilitado ainda. Ative os módulos que deseja usar "
                "(Prospecção, Cupons, Blog, E-mail Marketing e outros) para vê-los aqui "
                "e no menu lateral."
            ),
            "habilitar_modulos": "Habilitar módulos",
            "resumo_titulo": "Resumo de Prospecção",
            "resumo_legenda": "Empresas encontradas por semana",
            "oportunidades_titulo": "Oportunidades",
            "acoes_titulo": "Próximas ações",
            "empresas_titulo": "Empresas encontradas",
            "meta_titulo": "Meta de prospecção",
            "destaques_titulo": "Destaques",
        },
        "configuracoes": {
            "titulo": "Configurações Gerais do Sistema",
            "subtitulo": "Marca branca, tema padrão e gestão dos módulos do sistema.",
            "identidade_titulo": "Identidade do sistema",
            "modulos_titulo": "Módulos do sistema",
        },
    },
    # ------------------------------------------------------------------
    # Contas
    # ------------------------------------------------------------------
    "contas": {
        "login": {
            "titulo_aba": "Entrar",
            "titulo": "Acesse sua conta",
            "subtitulo": "Entre para continuar sua administração.",
            "rodape": "Acesso restrito à equipe. Suas credenciais são protegidas.",
        },
        "perfil": {
            "titulo": "Meu perfil",
            "subtitulo": "Atualize seus dados, foto, tema e senha de acesso.",
            "dados_titulo": "Dados do perfil",
            "senha_titulo": "Alterar senha",
        },
    },
    # ------------------------------------------------------------------
    # Páginas de erro
    # ------------------------------------------------------------------
    "erros": {
        "400": {
            "titulo": "Requisição inválida",
            "texto": "Não foi possível entender esta requisição. Verifique os dados e tente novamente.",
        },
        "403": {
            "titulo": "Acesso negado",
            "texto": (
                "Você não tem permissão para acessar esta página. Se acredita que isso é "
                "um engano, fale com um administrador."
            ),
        },
        "404": {
            "titulo": "Página não encontrada",
            "texto": "O endereço que você tentou acessar não existe ou foi movido.",
        },
        "500": {
            "titulo": "Erro interno",
            "texto": "Algo deu errado do nosso lado. Já estamos cientes — tente novamente em instantes.",
        },
    },
    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------
    "backup": {
        "lista": {
            "titulo": "Backup",
            "subtitulo": "Gere e baixe backups por módulo (fixtures) ou completos (banco + conteúdos).",
            "backups_titulo": "Backups gerados",
        },
        "novo": {
            "titulo": "Novo backup",
            "subtitulo": "Escolha o tipo e gere o backup. A execução é síncrona.",
            "dados_titulo": "Dados do backup",
            "tipos_titulo": "Sobre os tipos",
        },
    },
    # ------------------------------------------------------------------
    # Blog
    # ------------------------------------------------------------------
    "blog": {
        "lista": {
            "titulo": "Blog — Posts",
            "subtitulo": "Crie, valide e publique conteúdo otimizado para SEO, GEO e acessibilidade.",
            "posts_titulo": "Posts",
        },
        "categorias": {
            "titulo": "Blog — Categorias",
            "subtitulo": "Organize os posts em categorias (opcionalmente hierárquicas).",
            "categorias_titulo": "Categorias",
        },
        "tags": {
            "titulo": "Blog — Tags",
            "subtitulo": "Etiquete os posts com termos livres para facilitar a navegação.",
            "tags_titulo": "Tags",
        },
        "post_form": {
            "titulo_novo": "Novo post",
            "titulo_editar": "Editar post",
            "subtitulo": "A validação de SEO, GEO e acessibilidade roda a cada envio.",
            "publicacao_titulo": "Publicação",
            "analise_titulo": "Análise de qualidade",
            "seo_titulo": "SEO",
            "imagem_titulo": "Imagem de capa",
            "taxonomias_titulo": "Categorias & Tags",
        },
        "taxonomia_form": {
            "titulo_novo": "Nova {tipo}",
            "titulo_editar": "Editar {tipo}",
            "subtitulo": "Preencha os dados abaixo. O slug é gerado automaticamente quando deixado em branco.",
        },
        "confirmar_exclusao": {
            "titulo": "Confirmar exclusão",
            "subtitulo": "Esta ação não pode ser desfeita.",
        },
    },
    # ------------------------------------------------------------------
    # Cupons
    # ------------------------------------------------------------------
    "cupons": {
        "painel": {
            "titulo": "Cupons — Painel",
            "subtitulo": "Referencia {referencia} · {total} cliente{plural} no filtro atual.",
            "clientes_titulo": "Clientes",
        },
        "cupom_lista": {
            "titulo": "Cupons",
            "subtitulo": "{total} cupom(ns) no filtro atual.",
            "cupons_titulo": "Cupons",
        },
        "cupom_form": {
            "titulo_novo": "Novo cupom",
            "titulo_editar": "Editar cupom: {nome}",
            "subtitulo": "Defina o tipo de desconto, o valor e a vigencia do cupom.",
            "dados_titulo": "Dados do cupom",
            "tipos_titulo": "Tipos de desconto",
        },
        "cliente_lista": {
            "titulo": "Clientes",
            "subtitulo": "{total} cliente(s) no filtro atual.",
            "clientes_titulo": "Clientes",
        },
        "cliente_form": {
            "titulo_novo": "Novo cliente",
            "titulo_editar": "Editar: {nome}",
            "subtitulo": "Dados de contato, aniversario e mensalidade recorrente do cliente.",
            "dados_titulo": "Dados do cliente",
        },
        "cliente_detalhe": {
            "subtitulo": "{email} · {telefone} · aniversario {aniversario}",
            "valor_titulo": "Valor de {referencia}",
            "aplicar_titulo": "Aplicar cupom",
            "vigentes_titulo": "Cupons vigentes em {referencia}",
            "historico_titulo": "Historico de aplicacoes",
            "cobrancas_titulo": "Ultimas cobrancas",
            "excluir_titulo": "Excluir cliente",
        },
        "cobranca_lista": {
            "titulo": "Cobrancas",
            "subtitulo": "Referencia {referencia} · {total} cobranca(s) no filtro atual.",
            "cobrancas_titulo": "Cobrancas de {referencia}",
        },
        "cobranca_form": {
            "titulo": "Editar cobranca",
            "situacao_titulo": "Situacao da cobranca",
            "resumo_titulo": "Resumo",
        },
    },
    # ------------------------------------------------------------------
    # Marketing por e-mail
    # ------------------------------------------------------------------
    "email_marketing": {
        "campanhas": {
            "titulo": "Marketing por E-mail — Campanhas",
            "subtitulo": "Crie e dispare campanhas em massa pelo seu próprio remetente.",
            "campanhas_titulo": "Campanhas",
        },
        "campanha_detalhe": {
            "resultado_titulo": "Resultado do envio",
            "previa_titulo": "Prévia do corpo",
            "envios_titulo": "Últimos envios",
            "acoes_titulo": "Ações",
            "configuracao_titulo": "Configuração",
        },
        "campanha_form": {
            "titulo": "Nova campanha",
            "subtitulo": "Defina o assunto, o corpo e o remetente. Ela nasce como rascunho.",
            "dados_titulo": "Dados da campanha",
            "modelos_titulo": "Começar de um modelo",
            "marcadores_titulo": "Marcadores",
        },
        "configuracoes": {
            "titulo": "Configurações de envio",
            "subtitulo": (
                "Cadastre o remetente e o SMTP no próprio módulo. Use o tipo Console "
                "para testar sem SMTP."
            ),
            "remetentes_titulo": "Remetentes cadastrados",
            "nova_titulo": "Nova configuração",
            "smtp_legenda": "Servidor SMTP",
        },
        "contatos": {
            "titulo": "Contatos",
            "subtitulo": "Gerencie sua base de destinatários e importe novos contatos em massa.",
            "contatos_titulo": "Contatos",
            "importar_titulo": "Importar em massa",
        },
        "listas": {
            "titulo": "Listas",
            "subtitulo": "Agrupe contatos para segmentar suas campanhas.",
            "cadastradas_titulo": "Listas cadastradas",
            "nova_titulo": "Nova lista",
        },
        "templates": {
            "titulo": "Modelos de e-mail",
            "subtitulo": (
                "Biblioteca de 10 modelos prontos e 100% editáveis. Use-os como ponto "
                "de partida das campanhas."
            ),
            "disponiveis_titulo": "Modelos disponíveis",
            "novo_titulo": "Novo modelo",
        },
        "template_form": {
            "titulo": "Editar modelo",
        },
        "descadastrar": {
            "titulo_aba": "Descadastro",
            "invalido_titulo": "Link inválido",
            "concluido_titulo": "Descadastro concluído",
            "ja_descadastrado_titulo": "Você já está descadastrado",
            "confirmar_titulo": "Confirmar descadastro",
            "rodape": "{nome} — você recebeu este link em uma de nossas campanhas.",
        },
    },
    # ------------------------------------------------------------------
    # Kanban
    # ------------------------------------------------------------------
    "kanban": {
        "lista": {
            "titulo": "Kanban",
            "subtitulo": "Organize suas tarefas em quadros com colunas e cartões.",
            "vazio_titulo": "Nenhum quadro ainda",
        },
        "novo_quadro": {
            "titulo": "Novo quadro",
            "subtitulo": "Dê um nome ao quadro e, se quiser, uma breve descrição.",
            "configurar_titulo": "Configurar quadro",
        },
        "quadro": {
            "subtitulo_padrao": "Quadro de tarefas",
            "nova_coluna_titulo": "Nova coluna",
        },
    },
    # ------------------------------------------------------------------
    # Monitoramento
    # ------------------------------------------------------------------
    "monitoramento": {
        "lista": {
            "titulo": "Monitoramento",
            "subtitulo": "Acompanhe seus servidores/VPS por SSH: CPU, memória, disco e uptime.",
            "vazio_titulo": "Nenhum servidor cadastrado",
        },
        "form": {
            "titulo_novo": "Novo servidor",
            "titulo_editar": "Editar servidor",
            "subtitulo": (
                "Cadastre os dados de acesso SSH. As credenciais são armazenadas cifradas "
                "e nunca exibidas."
            ),
            "dados_titulo": "Dados do servidor",
            "credenciais_legenda": "Credenciais (cifradas)",
            "seguranca_titulo": "Segurança",
        },
        "detalhe": {
            "metricas_titulo": "Métricas atuais",
            "historico_titulo": "Histórico recente",
            "leituras_titulo": "Últimas leituras",
            "acoes_titulo": "Ações",
            "conexao_titulo": "Conexão",
        },
    },
    # ------------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------------
    "sla": {
        "lista": {
            "titulo": "SLA — Chamados",
            "subtitulo": "Acompanhe os chamados e o cumprimento dos prazos de atendimento.",
            "chamados_titulo": "Chamados",
        },
        "novo_chamado": {
            "titulo": "Novo chamado",
            "subtitulo": "Registre um chamado; os prazos de SLA são calculados pela política escolhida.",
            "dados_titulo": "Dados do chamado",
            "como_funciona_titulo": "Como o SLA funciona",
        },
        "politicas": {
            "titulo": "SLA — Políticas",
            "subtitulo": "Defina os prazos de resposta e resolução que regem os chamados.",
            "nova_titulo": "Nova política",
            "cadastradas_titulo": "Políticas cadastradas",
        },
        "detalhe": {
            "chamado_numero": "Chamado #{numero}",
            "prazo_titulo": "Prazo de resolução",
            "linha_tempo_titulo": "Linha do tempo",
            "aberto": "Chamado aberto",
            "primeira_resposta": "Primeira resposta",
            "resolucao": "Resolução",
            "descricao_titulo": "Descrição",
            "acoes_titulo": "Ações",
            "informacoes_titulo": "Informações",
        },
    },
    # ------------------------------------------------------------------
    # Prospecção (módulo de captura de leads com Google Maps / Places API)
    # ------------------------------------------------------------------
    "prospeccao": {
        # Rótulos canônicos dos problemas (badges, filtros, donut do dashboard).
        "problemas": {
            "sem_site": "Sem site",
            "site_desatualizado": "Site desatualizado",
            "apenas_instagram": "Apenas Instagram",
            "seo_fraco": "SEO fraco",
            "performance_baixa": "Performance baixa",
            "sem_ssl": "Sem SSL",
            "hospedagem_sem_site": "Hospedagem sem site",
            "nota_baixa": "Nota baixa",
            "poucas_avaliacoes": "Poucas avaliações",
            "sem_horario": "Sem horário",
            "horario_incompleto": "Horário incompleto",
            "poucas_fotos": "Poucas fotos",
            "perfil_desatualizado": "Perfil desatualizado",
            "fechada": "Fechada permanentemente",
            "nenhum": "Sem problemas",
            "nenhum_evidente": "Nenhum problema evidente",
        },
        "painel": {
            "titulo": "Painel da Prospecção",
            "subtitulo": (
                "Métricas do Google Places, chave da API e inteligência de análise do módulo."
            ),
            "nova_busca": "Nova busca",
            "metricas_titulo": "Diagnóstico dos perfis no Google",
            "metricas_legenda": (
                "{total} empresa(s) analisada(s) pela Google Places API (New). "
                "Clique em um indicador para ver as empresas."
            ),
            "metricas_vazio": (
                "Nenhuma empresa analisada pela Google Places API ainda. Salve a chave "
                "abaixo e execute uma busca."
            ),
            "metrica_nota_baixa": "Nota (rating) abaixo de {nota}",
            "metrica_sem_site": "Sem website (websiteUri nulo)",
            "metrica_poucas_avaliacoes": "Menos de {quantidade} avaliações",
            "metrica_horario": "Horário ausente ou mal preenchido",
            "metrica_fechadas": "Fechadas permanentemente",
            "metrica_poucas_fotos": "Sem fotos ou menos de {quantidade}",
            "metrica_desatualizado": "Sem atualização há mais de {meses} meses",
            "chave_titulo": "Chave da Google Places API (New)",
            "chave_desc": (
                "Cole aqui a chave criada no Google Cloud com a Places API (New) ativada. "
                "Ela é armazenada cifrada, nunca é exibida novamente e é usada em todas "
                "as buscas que não indicarem uma conexão específica."
            ),
            "chave_status_painel": "Chave configurada neste painel",
            "chave_status_ambiente": "Usando a variável de ambiente GOOGLE_MAPS_API_KEY",
            "chave_status_ausente": "Nenhuma chave configurada",
            "chave_salvar": "Salvar chave",
            "chave_testar": "Testar chave",
            "chave_remover": "Remover chave",
            "ia_titulo": "Inteligência artificial",
            "ia_desc": (
                "O motor de análise do módulo mede automaticamente, em cada empresa, nota "
                "(rating), website (websiteUri), quantidade de avaliações (userRatingCount), "
                "horário (regularOpeningHours), situação (businessStatus), fotos (photos) e "
                "tempo sem atualização. Opcionalmente, informe uma chave da API da Anthropic "
                "(Claude) para gerar diagnósticos e sugestões de abordagem em texto."
            ),
            "ia_status_ativa": "IA generativa ativa",
            "ia_status_sem_chave": "IA generativa sem chave — o motor de regras continua ativo",
            "ia_status_inativa": "IA generativa desativada — o motor de regras continua ativo",
            "ia_salvar": "Salvar configurações de IA",
            "ia_remover": "Remover chave da IA",
            "limiares_titulo": "Critérios de análise",
            "limiares_desc": (
                "Limites usados pelo motor de análise. Depois de alterar, clique em "
                "“Recalcular métricas” para aplicar às empresas já cadastradas."
            ),
            "limiares_salvar": "Salvar critérios",
            "recalcular": "Recalcular métricas",
            "msg_chave_salva": "Chave da Google Places API salva com sucesso.",
            "msg_chave_removida": "Chave da Google Places API removida deste painel.",
            "msg_chave_ok": "Conexão com a Google Places API (New) funcionando.",
            "msg_chave_erro": "Falha ao testar a chave: {erro}",
            "msg_ia_salva": "Configurações de IA salvas.",
            "msg_ia_removida": "Chave da IA removida.",
            "msg_limiares_salvos": "Critérios de análise salvos.",
            "msg_recalculado": "Métricas recalculadas para {total} empresa(s).",
            "msg_form_invalido": "Verifique os campos destacados.",
            "msg_acao_invalida": "Ação desconhecida.",
        },
        "formularios": {
            "chave_google_rotulo": "Chave da API do Google",
            "chave_google_ajuda": (
                "Começa com “AIza”. No Google Cloud, restrinja a chave à Places API (New)."
            ),
            "chave_placeholder_configurada": "•••••••• chave salva — cole uma nova para substituir",
            "chave_placeholder_vazia": "Cole aqui a chave da API",
            "ia_chave_rotulo": "Chave da API da Anthropic (Claude)",
            "ia_chave_ajuda": (
                "Opcional. Necessária apenas para os diagnósticos em texto gerados por IA. "
                "Deixe em branco para manter a chave atual."
            ),
            "ia_modelo_rotulo": "Modelo de IA",
            "ia_modelo_ajuda": "Identificador do modelo Claude usado nos diagnósticos (padrão: {modelo}).",
            "ia_ativa_rotulo": "Usar IA generativa nos diagnósticos",
            "ia_ativa_ajuda": "Desmarque para desativar a IA sem apagar a chave.",
            "limiar_nota_rotulo": "Nota mínima (rating)",
            "limiar_nota_ajuda": "Perfis com nota abaixo deste valor recebem o alerta “Nota baixa”. Padrão: 4.0.",
            "limiar_avaliacoes_rotulo": "Mínimo de avaliações (userRatingCount)",
            "limiar_avaliacoes_ajuda": "Abaixo deste número o perfil recebe “Poucas avaliações”. Padrão: 5.",
            "limiar_fotos_rotulo": "Mínimo de fotos (photos)",
            "limiar_fotos_ajuda": (
                "A API retorna no máximo 10 fotos por perfil. Abaixo deste número o perfil "
                "recebe “Poucas fotos”. Padrão: 3."
            ),
            "limiar_meses_rotulo": "Meses sem atualização",
            "limiar_meses_ajuda": (
                "Sem avaliações recentes há mais tempo que isso, o perfil é considerado "
                "desatualizado (a API não informa a data de edição do perfil). Padrão: 6."
            ),
            "erro_chave_obrigatoria": "Informe a chave da API.",
            "erro_chave_tamanho": "A chave tem tamanho inválido.",
            "erro_chave_formato": "A chave contém caracteres inválidos.",
            "erro_modelo": "Informe um identificador de modelo válido (ex.: {modelo}).",
            "conexao_chave_rotulo": "Chave da API",
            "conexao_chave_ajuda": "A chave é armazenada cifrada e nunca é exibida novamente.",
            "busca_conexao_vazio": "Usar a chave do Painel",
            "busca_conexao_ajuda": "Opcional. Sem conexão, a busca usa a chave salva no Painel do módulo.",
            "termo_placeholder": "Ex.: restaurantes",
            "localizacao_placeholder": "Ex.: Barra da Tijuca, Rio de Janeiro",
            "erro_termo_curto": "O termo deve ter ao menos 2 caracteres.",
            "erro_localizacao_curta": "A localização deve ter ao menos 2 caracteres.",
            "erro_raio_obrigatorio": "Informe o raio em metros.",
            "erro_raio_intervalo": "O raio deve estar entre {minimo} e {maximo} metros.",
        },
        "lista": {
            "titulo": "Empresas",
            "subtitulo": "Todos os leads encontrados e qualificados na sua prospecção.",
            "nova_busca": "Nova busca",
            "cartao_titulo": "Empresas encontradas",
            "filtro_aria": "Filtrar empresas",
            "filtro_status": "Status",
            "filtro_problema": "Problema",
            "todos": "Todos",
            "filtrar": "Filtrar",
            "limpar": "Limpar",
            "col_empresa": "Empresa",
            "col_tempo": "Tempo de mercado",
            "col_responsavel": "Responsável",
            "col_email": "E-mail",
            "col_instagram": "Instagram",
            "col_dominio": "Domínio",
            "col_whatsapp": "WhatsApp",
            "col_nota": "Nota Google",
            "col_score": "Score",
            "col_problemas": "Problemas",
            "vazio": "Nenhuma empresa corresponde aos filtros selecionados.",
            "vazio_dashboard": "Nenhuma empresa encontrada ainda. Crie uma nova busca para começar.",
            "ver_todas": "Ver todas",
            "paginacao_aria": "Paginação",
            "anterior": "Anterior",
            "proxima": "Próxima",
            "pagina": "Página {atual} de {total}",
        },
        "detalhe": {
            "subtitulo_padrao": "Empresa",
            "voltar": "Voltar",
            "tempo_nao_informado": "Tempo de mercado não informado",
            "oportunidade": "oportunidade",
            "problemas_titulo": "Problemas detectados",
            "contatos_titulo": "Contatos",
            "responsavel": "Responsável",
            "email": "E-mail",
            "telefone": "Telefone",
            "whatsapp": "WhatsApp",
            "instagram": "Instagram",
            "website": "Website",
            "dominio": "Domínio",
            "endereco": "Endereço",
            "observacoes_titulo": "Observações",
            "scores_titulo": "Scores",
            "score_seo": "SEO",
            "score_performance": "Performance",
            "score_oportunidade": "Oportunidade",
            "aria_seo": "Score de SEO",
            "aria_performance": "Score de performance",
            "aria_oportunidade": "Score de oportunidade",
            "sinais_titulo": "Sinais técnicos",
            "possui_site": "Possui site",
            "site_desatualizado": "Site desatualizado",
            "apenas_instagram": "Apenas Instagram",
            "possui_ssl": "Possui SSL",
            "hospedagem_sem_site": "Hospedagem sem site",
            "desconhecido": "Desconhecido",
            "informacoes_titulo": "Informações",
            "categoria": "Categoria",
            "data_fundacao": "Data de fundação",
            "localizacao": "Localização",
            "criada_em": "Criada em",
            "atualizada_em": "Atualizada em",
            "google_titulo": "Perfil no Google (Places API)",
            "google_nao_analisado": (
                "Esta empresa ainda não tem métricas da Google Places API. Clique em "
                "“Atualizar dados do Google”."
            ),
            "nota": "Nota (rating)",
            "avaliacoes": "Avaliações (userRatingCount)",
            "fotos": "Fotos (photos)",
            "horario": "Horário (regularOpeningHours)",
            "situacao": "Situação (businessStatus)",
            "ultima_atividade": "Última atividade detectada",
            "sem_atividade": "Nenhuma avaliação datada",
            "abrir_maps": "Abrir no Google Maps",
            "atualizar_google": "Atualizar dados do Google",
            "analisado_em": "Dados do Google de {data}",
            "horario_ok": "Preenchido",
            "horario_ausente": "Ausente",
            "horario_incompleto": "Incompleto",
            "status_operacional": "Em funcionamento",
            "status_fechada_temporariamente": "Fechada temporariamente",
            "status_fechada": "Fechada permanentemente",
            "status_desconhecido": "Não informado",
            "diagnostico_titulo": "Diagnóstico do motor de análise",
            "diagnostico_vazio": "Sem diagnóstico ainda. Atualize os dados do Google.",
            "ia_titulo": "Diagnóstico com IA",
            "ia_gerar": "Gerar diagnóstico com IA",
            "ia_regerar": "Gerar novamente",
            "ia_gerado_em": "Gerado em {data}",
            "ia_vazio": "Nenhum diagnóstico com IA gerado ainda.",
            "ia_sem_chave": "Configure a chave da IA no Painel do módulo para habilitar esta função.",
            "ia_inativa": "A IA generativa está desativada no Painel do módulo.",
            "ir_painel": "Ir para o Painel",
            "msg_ia_ok": "Diagnóstico com IA gerado.",
            "msg_ia_erro": "Não foi possível gerar o diagnóstico com IA: {erro}",
            "msg_google_ok": "Dados do Google atualizados.",
            "msg_google_erro": "Não foi possível atualizar os dados do Google: {erro}",
            "msg_google_sem_place": "Esta empresa não possui identificador (place_id) do Google.",
        },
        "conexoes": {
            "titulo": "Conexões",
            "subtitulo": "Gerencie as credenciais usadas nas buscas de prospecção.",
            "lista_titulo": "Conexões cadastradas",
            "col_nome": "Nome",
            "col_chave": "Chave",
            "col_status": "Status",
            "col_criada_por": "Criada por",
            "col_criada_em": "Criada em",
            "chave_configurada": "Chave configurada",
            "sem_chave": "Sem chave",
            "ativa": "Ativa",
            "inativa": "Inativa",
            "vazio": "Nenhuma conexão cadastrada ainda.",
            "nova_titulo": "Nova conexão",
            "salvar": "Salvar conexão",
            "dica": (
                "Dica: o caminho mais simples é salvar a chave no Painel do módulo. Use "
                "conexões apenas se precisar de chaves diferentes por busca."
            ),
            "msg_criada": "Conexão criada com sucesso.",
        },
        "nova_busca": {
            "titulo": "Nova busca",
            "subtitulo": "Defina o termo, a localização e o raio para encontrar novas empresas.",
            "configurar_titulo": "Configurar busca",
            "criar": "Criar busca",
            "recentes_titulo": "Buscas recentes",
            "col_termo": "Termo",
            "col_localizacao": "Localização",
            "col_raio": "Raio",
            "col_status": "Status",
            "col_resultados": "Resultados",
            "col_acao": "Ação",
            "executar": "Executar",
            "vazio": "Nenhuma busca criada ainda.",
            "msg_criada": "Busca criada. Clique em Executar para iniciar a prospecção.",
            "msg_executada": "Busca executada: {total} empresa(s) processada(s).",
            "msg_erro": "Não foi possível executar a busca. Tente novamente.",
            "msg_sem_chave": (
                "Nenhuma chave da Google Places API configurada. Salve a chave no Painel do módulo."
            ),
        },
        # Textos do motor de análise (diagnóstico gerado por regras).
        "diagnostico": {
            "nota_baixa": "nota {nota} (abaixo de {limite})",
            "sem_avaliacoes": "nenhuma avaliação no Google",
            "poucas_avaliacoes": "apenas {quantidade} avaliação(ões) (mínimo {limite})",
            "sem_site": "sem website cadastrado no perfil",
            "sem_horario": "horário de funcionamento ausente",
            "horario_incompleto": "horário de funcionamento incompleto ou mal preenchido",
            "sem_fotos": "nenhuma foto no perfil",
            "poucas_fotos": "apenas {quantidade} foto(s) (mínimo {limite})",
            "sem_atividade": "nenhuma atividade recente detectada (sem avaliações datadas)",
            "desatualizado": "sem atualização há cerca de {meses} meses (limite: {limite})",
            "fechada": (
                "O Google marca esta empresa como FECHADA PERMANENTEMENTE. Descarte o lead "
                "ou confirme a informação antes do contato."
            ),
            "cabecalho": "Pontos de atenção no perfil do Google: {itens}.",
            "sem_alertas": (
                "O perfil no Google está completo nos critérios analisados (nota, avaliações, "
                "site, horário, fotos e atualização)."
            ),
            "prioridade": "Prioridade {prioridade} (score do perfil {score}/100).",
            "prioridade_alta": "alta",
            "prioridade_media": "média",
            "prioridade_baixa": "baixa",
            "prioridade_descartar": "descartar",
            "sugestoes": "Sugestões de abordagem: {itens}.",
            "sug_sem_site": "criação de site profissional",
            "sug_nota": "gestão de reputação e resposta às avaliações",
            "sug_avaliacoes": "campanha de captação de avaliações",
            "sug_horario": "atualização do horário de funcionamento no Perfil da Empresa",
            "sug_fotos": "produção de fotos profissionais do negócio",
            "sug_atualizacao": "rotina de publicações e atualização do perfil",
        },
        # Mensagens de erro da integração com a Google Places API (New).
        "google": {
            "erro_sem_chave": (
                "Chave da Google Places API ausente. Salve a chave no Painel do módulo, "
                "cadastre uma conexão ativa ou defina GOOGLE_MAPS_API_KEY."
            ),
            "erro_chave_invalida": (
                "Chave da Google Places API inválida, sem permissão ou com a Places API (New) "
                "desativada no projeto."
            ),
            "erro_http": "A Google Places API respondeu com erro HTTP {status}.",
            "erro_rede": "Falha de conexão com a Google Places API.",
        },
        # Mensagens da IA generativa (Claude).
        "ia": {
            "erro_sem_chave": "Chave da API da Anthropic não configurada.",
            "erro_inativa": "IA generativa desativada.",
            "erro_sdk": "Biblioteca “anthropic” não instalada (pip install -r requirements.txt).",
            "erro_autenticacao": "Chave da API da Anthropic inválida ou sem permissão.",
            "erro_modelo": "Modelo de IA inválido ou indisponível ({modelo}).",
            "erro_limite": "Limite de uso da API atingido. Tente novamente em instantes.",
            "erro_conexao": "Falha de conexão com a API da Anthropic.",
            "erro_recusa": "A IA não pôde gerar este diagnóstico.",
            "erro_vazio": "A IA não retornou texto.",
            "erro_api": "Erro da API da Anthropic (HTTP {status}).",
        },
    },
}


class _Parametros(dict):
    """Dicionário de formatação que preserva marcadores ausentes (``{x}``)."""

    def __missing__(self, chave: str) -> str:
        return "{" + chave + "}"


def _resolver(chave: str) -> Any:
    """Percorre ``TEXTOS`` pelo caminho pontuado; ``None`` se não existir."""
    atual: Any = TEXTOS
    for parte in (chave or "").split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


def existe(chave: str) -> bool:
    """Indica se ``chave`` aponta para um texto (string) existente."""
    return isinstance(_resolver(chave), str)


def texto(chave: str, padrao: str | None = None, **parametros: Any) -> str:
    """Retorna o texto da ``chave`` (caminho pontuado), já formatado.

    Args:
        chave: caminho pontuado (ex.: ``"prospeccao.painel.titulo"``).
        padrao: valor devolvido se a chave não existir (padrão: a própria chave).
        **parametros: valores dos marcadores ``{nome}`` do texto.

    Nunca levanta: chave ausente é registrada no log e devolve ``padrao``
    (ou a própria chave, para ficar visível na tela e fácil de corrigir).
    """
    valor = _resolver(chave)
    if not isinstance(valor, str):
        logger.warning("Texto não encontrado para a chave '%s'.", chave)
        return padrao if padrao is not None else chave
    if parametros:
        try:
            valor = valor.format_map(_Parametros(parametros))
        except (ValueError, IndexError, AttributeError):
            logger.warning("Falha ao formatar o texto '%s'.", chave)
    return valor


def secao(chave: str) -> dict:
    """Retorna um dicionário de textos (ex.: ``secao("prospeccao.problemas")``)."""
    valor = _resolver(chave)
    return dict(valor) if isinstance(valor, dict) else {}


def todas_as_chaves(base: dict | None = None, prefixo: str = "") -> set[str]:
    """Conjunto de todos os caminhos pontuados que apontam para textos."""
    base = TEXTOS if base is None else base
    chaves: set[str] = set()
    for nome, valor in base.items():
        caminho = f"{prefixo}{nome}"
        if isinstance(valor, dict):
            chaves |= todas_as_chaves(valor, f"{caminho}.")
        elif isinstance(valor, str):
            chaves.add(caminho)
    return chaves

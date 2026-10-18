# -*- coding: utf-8 -*-
"""
Biblioteca de templates prontos de e-mail marketing.

Este modulo nao depende do Django nem de nenhum outro pacote: ele apenas
define a constante TEMPLATES_PRONTOS, uma lista de dicionarios em Python
puro. Cada dicionario representa um modelo de e-mail HTML profissional,
responsivo (baseado em tabelas, compativel com Gmail/Outlook/Apple Mail) e
100% editavel pelo usuario final.

Marcadores de personalizacao usados nos templates (o motor de envio deve
fazer um str.replace simples destes marcadores antes de disparar o
e-mail):

    {{ nome }}               -> primeiro nome / nome do contato
    {{ empresa }}             -> empresa do contato
    {{ email }}               -> e-mail do contato
    {{ link_descadastro }}    -> link de descadastro (obrigatorio em todos)

Todos os 10 templates contem, no rodape, o link de descadastro
{{ link_descadastro }} e uma frase explicando que o contato recebe o
e-mail por ter se inscrito anteriormente.

Cada item da lista TEMPLATES_PRONTOS possui exatamente as chaves:
    "nome"        (str)  - nome do template (para exibicao no catalogo)
    "descricao"   (str)  - descricao curta do template
    "categoria"   (str)  - uma das 10 categorias fixas do catalogo
    "corpo_html"  (str)  - HTML completo do e-mail
    "corpo_texto" (str)  - versao em texto puro equivalente ao HTML
"""

# ---------------------------------------------------------------------------
# Blocos HTML compartilhados (cabecalho, cabecalho "simples" e rodape).
# Sao concatenados com o conteudo especifico de cada template para montar
# o documento HTML completo de cada e-mail.
# ---------------------------------------------------------------------------

_HEAD = """<!DOCTYPE html>
<html lang='pt-br'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Sua Empresa</title>
<style>
  @media only screen and (max-width: 600px) {
    .container-600 { width: 100% !important; }
    .mobile-padding { padding-left: 20px !important; padding-right: 20px !important; }
  }
</style>
</head>
<body style='margin:0; padding:0; background-color:#f3f4f7;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='background-color:#f3f4f7; width:100%;'>
<tr>
<td align='center' style='padding:24px 12px;'>
<table role='presentation' class='container-600' width='600' cellpadding='0' cellspacing='0' border='0' style='width:600px; max-width:600px; background-color:#ffffff; border-radius:10px; overflow:hidden; border:1px solid #ececf2;'>
<tr>
<td bgcolor='#7c5cff' class='mobile-padding' style='background-color:#7c5cff; padding:26px 32px;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td style='font-family:Arial, Helvetica, sans-serif; font-size:20px; font-weight:bold; color:#ffffff; letter-spacing:0.4px;'>SUA EMPRESA</td>
</tr>
</table>
</td>
</tr>
"""

_HEAD_SIMPLES = """<!DOCTYPE html>
<html lang='pt-br'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Sua Empresa</title>
<style>
  @media only screen and (max-width: 600px) {
    .container-600 { width: 100% !important; }
    .mobile-padding { padding-left: 20px !important; padding-right: 20px !important; }
  }
</style>
</head>
<body style='margin:0; padding:0; background-color:#f3f4f7;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='background-color:#f3f4f7; width:100%;'>
<tr>
<td align='center' style='padding:24px 12px;'>
<table role='presentation' class='container-600' width='600' cellpadding='0' cellspacing='0' border='0' style='width:600px; max-width:600px; background-color:#ffffff; border:1px solid #ececf2;'>
<tr>
<td class='mobile-padding' style='padding:20px 32px; border-bottom:1px solid #ececf2;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td style='font-family:Georgia, serif; font-size:15px; color:#7c5cff; letter-spacing:0.3px;'>Sua Empresa</td>
</tr>
</table>
</td>
</tr>
"""

_FOOT = """<tr>
<td class='mobile-padding' style='padding:22px 32px; background-color:#f7f7fb; border-top:1px solid #ececf2;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td style='font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:18px; color:#8a8a99; text-align:center;'>
Voce esta recebendo este e-mail porque {{ email }} se inscreveu para receber novidades e comunicacoes de Sua Empresa.<br>
<a href='{{ link_descadastro }}' style='color:#7c5cff; text-decoration:underline;'>Cancelar inscricao / Descadastrar</a>
<br>
Sua Empresa &middot; Todos os direitos reservados
</td>
</tr>
</table>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""

_TXT_FOOTER = """
--
Voce esta recebendo este e-mail porque {{ email }} se inscreveu para receber novidades e comunicacoes de Sua Empresa.
Para cancelar sua inscricao e nao receber mais nossos e-mails, acesse: {{ link_descadastro }}
"""

# ---------------------------------------------------------------------------
# 1. Boas-vindas
# ---------------------------------------------------------------------------

_BODY_1 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>Ola, {{ nome }}! Seja muito bem-vindo(a).</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Ficamos muito felizes em ter voce e a equipe da {{ empresa }} com a gente. A partir de agora, todas as nossas novidades, dicas e conteudos exclusivos vao chegar direto na sua caixa de entrada, no e-mail {{ email }}.</p>
<p style='margin:0 0 8px 0; font-size:15px; line-height:24px; color:#51525c;'>Para voce aproveitar ao maximo, separamos os primeiros passos:</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:0 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td width='24' valign='top' style='font-size:15px; color:#7c5cff; font-weight:bold; padding:4px 8px 4px 0;'>1.</td>
<td style='font-size:15px; line-height:22px; color:#333333; padding:4px 0;'>Complete seu perfil com seus dados e preferencias.</td>
</tr>
<tr>
<td width='24' valign='top' style='font-size:15px; color:#7c5cff; font-weight:bold; padding:4px 8px 4px 0;'>2.</td>
<td style='font-size:15px; line-height:22px; color:#333333; padding:4px 0;'>Explore o painel e conheca as principais funcionalidades.</td>
</tr>
<tr>
<td width='24' valign='top' style='font-size:15px; color:#7c5cff; font-weight:bold; padding:4px 8px 4px 0;'>3.</td>
<td style='font-size:15px; line-height:22px; color:#333333; padding:4px 0;'>Fale com nosso time de suporte sempre que precisar de ajuda.</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:16px 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Acessar minha conta</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#51525c;'>
Um abraco,<br>Equipe Sua Empresa
</td>
</tr>
"""

_TXT_1 = """Ola, {{ nome }}! Seja muito bem-vindo(a).

Ficamos muito felizes em ter voce e a equipe da {{ empresa }} com a gente. A partir de agora, todas as nossas novidades, dicas e conteudos exclusivos vao chegar direto na sua caixa de entrada, no e-mail {{ email }}.

Para voce aproveitar ao maximo, separamos os primeiros passos:
1. Complete seu perfil com seus dados e preferencias.
2. Explore o painel e conheca as principais funcionalidades.
3. Fale com nosso time de suporte sempre que precisar de ajuda.

Acessar minha conta: [link]

Um abraco,
Equipe Sua Empresa
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 2. Newsletter
# ---------------------------------------------------------------------------

_BODY_2 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 4px 0; font-size:13px; font-weight:bold; letter-spacing:1px; color:#7c5cff; text-transform:uppercase;'>Newsletter mensal</p>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>Novidades do mes para voce, {{ nome }}</p>
<p style='margin:0 0 8px 0; font-size:15px; line-height:24px; color:#51525c;'>Separamos os destaques do mes para a equipe da {{ empresa }}. Boa leitura!</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 0 32px; font-family:Arial, Helvetica, sans-serif; border-top:1px solid #ececf2;'>
<p style='margin:16px 0 6px 0; font-size:17px; line-height:22px; font-weight:bold; color:#1f2130;'>1. Como organizar sua rotina em 3 passos</p>
<p style='margin:0 0 8px 0; font-size:14px; line-height:22px; color:#51525c;'>Reunimos as praticas mais simples para voce ganhar tempo no dia a dia e manter o foco no que realmente importa.</p>
<p style='margin:0 0 8px 0;'><a href='#' style='font-size:14px; font-weight:bold; color:#7c5cff; text-decoration:none;'>Continuar lendo &rarr;</a></p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:8px 32px 0 32px; font-family:Arial, Helvetica, sans-serif; border-top:1px solid #ececf2;'>
<p style='margin:16px 0 6px 0; font-size:17px; line-height:22px; font-weight:bold; color:#1f2130;'>2. Bastidores: o que mudou na nossa plataforma</p>
<p style='margin:0 0 8px 0; font-size:14px; line-height:22px; color:#51525c;'>Contamos os detalhes das ultimas atualizacoes e o que vem por ai nos proximos meses.</p>
<p style='margin:0 0 8px 0;'><a href='#' style='font-size:14px; font-weight:bold; color:#7c5cff; text-decoration:none;'>Continuar lendo &rarr;</a></p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:8px 32px 0 32px; font-family:Arial, Helvetica, sans-serif; border-top:1px solid #ececf2;'>
<p style='margin:16px 0 6px 0; font-size:17px; line-height:22px; font-weight:bold; color:#1f2130;'>3. Historias de quem usa a Sua Empresa todos os dias</p>
<p style='margin:0 0 8px 0; font-size:14px; line-height:22px; color:#51525c;'>Clientes reais contam como economizaram tempo e melhoraram seus resultados no ultimo trimestre.</p>
<p style='margin:0 0 8px 0;'><a href='#' style='font-size:14px; font-weight:bold; color:#7c5cff; text-decoration:none;'>Continuar lendo &rarr;</a></p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#51525c; border-top:1px solid #ececf2;'>
Obrigado por acompanhar nossas novidades. Ate a proxima edicao!
</td>
</tr>
"""

_TXT_2 = """NEWSLETTER MENSAL

Novidades do mes para voce, {{ nome }}

Separamos os destaques do mes para a equipe da {{ empresa }}. Boa leitura!

1. Como organizar sua rotina em 3 passos
Reunimos as praticas mais simples para voce ganhar tempo no dia a dia e manter o foco no que realmente importa.
Continuar lendo: [link]

2. Bastidores: o que mudou na nossa plataforma
Contamos os detalhes das ultimas atualizacoes e o que vem por ai nos proximos meses.
Continuar lendo: [link]

3. Historias de quem usa a Sua Empresa todos os dias
Clientes reais contam como economizaram tempo e melhoraram seus resultados no ultimo trimestre.
Continuar lendo: [link]

Obrigado por acompanhar nossas novidades. Ate a proxima edicao!
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 3. Promocao
# ---------------------------------------------------------------------------

_BODY_3 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>{{ nome }}, preparamos uma oferta especial para voce</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Por tempo limitado, voce garante uma condicao exclusiva em qualquer plano da Sua Empresa.</p>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:8px 32px 16px 32px;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='background-color:#f1edff; border-radius:8px;'>
<tr>
<td align='center' style='padding:28px 16px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0; font-size:42px; line-height:46px; font-weight:bold; color:#7c5cff;'>25% OFF</p>
<p style='margin:6px 0 0 0; font-size:14px; line-height:20px; color:#51525c;'>em todos os planos, por tempo limitado</p>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:0 32px 8px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; line-height:24px; color:#51525c;'>
A promocao e valida ate o fim deste mes e pode ser aplicada automaticamente na sua proxima renovacao ou em uma nova assinatura.
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:16px 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Aproveitar a oferta</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:18px; color:#8a8a99;'>
Promocao valida enquanto durar o estoque de vagas promocionais. Consulte condicoes completas em nosso site.
</td>
</tr>
"""

_TXT_3 = """{{ nome }}, preparamos uma oferta especial para voce

Por tempo limitado, voce garante uma condicao exclusiva em qualquer plano da Sua Empresa.

>>> 25% OFF em todos os planos, por tempo limitado <<<

A promocao e valida ate o fim deste mes e pode ser aplicada automaticamente na sua proxima renovacao ou em uma nova assinatura.

Aproveitar a oferta: [link]

Promocao valida enquanto durar o estoque de vagas promocionais. Consulte condicoes completas em nosso site.
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 4. Anuncio
# ---------------------------------------------------------------------------

_BODY_4 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 4px 0; font-size:13px; font-weight:bold; letter-spacing:1px; color:#7c5cff; text-transform:uppercase;'>Novidade</p>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>{{ nome }}, temos uma novidade para voce</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Depois de meses de trabalho, lancamos um novo recurso pensado para facilitar ainda mais o seu dia a dia com a Sua Empresa.</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:0 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td style='padding:10px 0; border-bottom:1px solid #ececf2; font-size:14px; line-height:20px; color:#333333;'><strong style='color:#1f2130;'>Relatorios automaticos</strong> &mdash; acompanhe seus resultados sem precisar montar planilhas.</td>
</tr>
<tr>
<td style='padding:10px 0; border-bottom:1px solid #ececf2; font-size:14px; line-height:20px; color:#333333;'><strong style='color:#1f2130;'>Integracoes novas</strong> &mdash; conecte suas ferramentas favoritas em poucos cliques.</td>
</tr>
<tr>
<td style='padding:10px 0; font-size:14px; line-height:20px; color:#333333;'><strong style='color:#1f2130;'>Suporte por chat</strong> &mdash; fale com nosso time em tempo real, direto da plataforma.</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:16px 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Conhecer a novidade</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#51525c;'>
Qualquer duvida, e so responder este e-mail. Vamos adorar ouvir o que voce achou!
</td>
</tr>
"""

_TXT_4 = """{{ nome }}, temos uma novidade para voce

Depois de meses de trabalho, lancamos um novo recurso pensado para facilitar ainda mais o seu dia a dia com a Sua Empresa.

- Relatorios automaticos: acompanhe seus resultados sem precisar montar planilhas.
- Integracoes novas: conecte suas ferramentas favoritas em poucos cliques.
- Suporte por chat: fale com nosso time em tempo real, direto da plataforma.

Conhecer a novidade: [link]

Qualquer duvida, e so responder este e-mail. Vamos adorar ouvir o que voce achou!
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 5. Evento
# ---------------------------------------------------------------------------

_BODY_5 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 4px 0; font-size:13px; font-weight:bold; letter-spacing:1px; color:#7c5cff; text-transform:uppercase;'>Convite</p>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>{{ nome }}, voce esta convidado(a)!</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Vamos realizar um evento exclusivo para clientes e parceiros da Sua Empresa, com conteudo pratico e novidades em primeira mao. Sera um prazer contar com a presenca da equipe da {{ empresa }}.</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:0 32px 16px 32px;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='background-color:#f7f7fb; border-radius:8px;'>
<tr>
<td style='padding:20px 24px; font-family:Arial, Helvetica, sans-serif;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td width='90' style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0;'>Data:</td>
<td style='font-size:14px; color:#51525c; padding:6px 0;'>18 de setembro de 2026 (sexta-feira)</td>
</tr>
<tr>
<td width='90' style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0;'>Horario:</td>
<td style='font-size:14px; color:#51525c; padding:6px 0;'>19h00 (horario de Brasilia)</td>
</tr>
<tr>
<td width='90' style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0;'>Local:</td>
<td style='font-size:14px; color:#51525c; padding:6px 0;'>Online, transmissao ao vivo (link enviado apos a confirmacao)</td>
</tr>
</table>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:8px 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Confirmar minha presenca</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:18px; color:#8a8a99;'>
As vagas sao limitadas, garanta a sua o quanto antes.
</td>
</tr>
"""

_TXT_5 = """{{ nome }}, voce esta convidado(a)!

Vamos realizar um evento exclusivo para clientes e parceiros da Sua Empresa, com conteudo pratico e novidades em primeira mao. Sera um prazer contar com a presenca da equipe da {{ empresa }}.

Data: 18 de setembro de 2026 (sexta-feira)
Horario: 19h00 (horario de Brasilia)
Local: Online, transmissao ao vivo (link enviado apos a confirmacao)

Confirmar minha presenca: [link]

As vagas sao limitadas, garanta a sua o quanto antes.
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 6. Follow-up
# ---------------------------------------------------------------------------

_BODY_6 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>Ola {{ nome }}, tudo bem?</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Passando para saber como esta sendo a sua experiencia com a Sua Empresa desde o nosso ultimo contato com a equipe da {{ empresa }}. Ficamos a disposicao para o que for preciso.</p>
<p style='margin:0 0 8px 0; font-size:15px; line-height:24px; color:#51525c;'>Podemos te ajudar com:</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:0 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td width='20' valign='top' style='font-size:15px; color:#7c5cff; padding:4px 8px 4px 0;'>&bull;</td>
<td style='font-size:15px; line-height:22px; color:#333333; padding:4px 0;'>Duvidas sobre como usar algum recurso.</td>
</tr>
<tr>
<td width='20' valign='top' style='font-size:15px; color:#7c5cff; padding:4px 8px 4px 0;'>&bull;</td>
<td style='font-size:15px; line-height:22px; color:#333333; padding:4px 0;'>Ajustes no seu plano ou na sua conta.</td>
</tr>
<tr>
<td width='20' valign='top' style='font-size:15px; color:#7c5cff; padding:4px 8px 4px 0;'>&bull;</td>
<td style='font-size:15px; line-height:22px; color:#333333; padding:4px 0;'>Sugestoes e feedback sobre a sua experiencia.</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:16px 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Falar com nosso time</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#51525c;'>
Um abraco,<br>Equipe Sua Empresa
</td>
</tr>
"""

_TXT_6 = """Ola {{ nome }}, tudo bem?

Passando para saber como esta sendo a sua experiencia com a Sua Empresa desde o nosso ultimo contato com a equipe da {{ empresa }}. Ficamos a disposicao para o que for preciso.

Podemos te ajudar com:
- Duvidas sobre como usar algum recurso.
- Ajustes no seu plano ou na sua conta.
- Sugestoes e feedback sobre a sua experiencia.

Falar com nosso time: [link]

Um abraco,
Equipe Sua Empresa
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 7. Reengajamento
# ---------------------------------------------------------------------------

_BODY_7 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>{{ nome }}, sentimos a sua falta</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Notamos que faz um tempo que voce nao acessa a Sua Empresa. Muita coisa mudou desde a sua ultima visita e preparamos algo especial para voce voltar.</p>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:8px 32px 16px 32px;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='background-color:#f1edff; border-radius:8px;'>
<tr>
<td align='center' style='padding:24px 16px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0; font-size:16px; line-height:22px; font-weight:bold; color:#1f2130;'>Volte agora e ganhe 30 dias de acesso gratuito</p>
<p style='margin:6px 0 0 0; font-size:13px; line-height:20px; color:#51525c;'>valido somente para quem reativar a conta esta semana</p>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:0 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Voltar agora</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#51525c;'>
Se preferir nao receber mais nossos e-mails, voce pode atualizar suas preferencias a qualquer momento no rodape desta mensagem.
</td>
</tr>
"""

_TXT_7 = """{{ nome }}, sentimos a sua falta

Notamos que faz um tempo que voce nao acessa a Sua Empresa. Muita coisa mudou desde a sua ultima visita e preparamos algo especial para voce voltar.

Volte agora e ganhe 30 dias de acesso gratuito (valido somente para quem reativar a conta esta semana).

Voltar agora: [link]

Se preferir nao receber mais nossos e-mails, voce pode atualizar suas preferencias a qualquer momento pelo link abaixo.
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 8. Transacional
# ---------------------------------------------------------------------------

_BODY_8 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>Tudo certo, {{ nome }}!</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Confirmamos o seu pedido na Sua Empresa. Abaixo estao os detalhes para o seu controle.</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:0 32px 16px 32px;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='background-color:#f7f7fb; border-radius:8px;'>
<tr>
<td style='padding:20px 24px; font-family:Arial, Helvetica, sans-serif;'>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0; border-bottom:1px solid #ececf2;'>Numero do pedido</td>
<td align='right' style='font-size:14px; color:#51525c; padding:6px 0; border-bottom:1px solid #ececf2;'>#000123</td>
</tr>
<tr>
<td style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0; border-bottom:1px solid #ececf2;'>Data</td>
<td align='right' style='font-size:14px; color:#51525c; padding:6px 0; border-bottom:1px solid #ececf2;'>25/08/2026</td>
</tr>
<tr>
<td style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0; border-bottom:1px solid #ececf2;'>Valor total</td>
<td align='right' style='font-size:14px; color:#51525c; padding:6px 0; border-bottom:1px solid #ececf2;'>R$ 197,00</td>
</tr>
<tr>
<td style='font-size:14px; font-weight:bold; color:#1f2130; padding:6px 0;'>Status</td>
<td align='right' style='font-size:14px; color:#2e8b57; font-weight:bold; padding:6px 0;'>Confirmado</td>
</tr>
</table>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:8px 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Ver detalhes do pedido</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:22px; color:#51525c;'>
Este e-mail confirma o pedido feito com o endereco {{ email }}. Qualquer duvida, fale com o nosso suporte.
</td>
</tr>
"""

_TXT_8 = """Tudo certo, {{ nome }}!

Confirmamos o seu pedido na Sua Empresa. Abaixo estao os detalhes para o seu controle.

Numero do pedido: #000123
Data: 25/08/2026
Valor total: R$ 197,00
Status: Confirmado

Ver detalhes do pedido: [link]

Este e-mail confirma o pedido feito com o endereco {{ email }}. Qualquer duvida, fale com o nosso suporte.
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 9. Simples
# ---------------------------------------------------------------------------

_BODY_9 = """<tr>
<td class='mobile-padding' style='padding:32px 32px 8px 32px; font-family:Georgia, serif;'>
<p style='margin:0 0 16px 0; font-size:16px; line-height:26px; color:#333333;'>Ola, {{ nome }},</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:26px; color:#333333;'>Escrevo para compartilhar algumas novidades importantes sobre a Sua Empresa. Preferimos manter este contato simples e direto, sem enfeites, para ir direto ao que interessa.</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:26px; color:#333333;'>Nos ultimos meses, temos trabalhado para melhorar a experiencia de quem confia no nosso trabalho, incluindo a equipe da {{ empresa }}. Ainda ha muito por vir, e voce vai acompanhar tudo por aqui.</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:26px; color:#333333;'>Se quiser conversar, e so responder este e-mail. Temos o maior prazer em ouvir voce.</p>
<p style='margin:24px 0 0 0; font-size:15px; line-height:24px; color:#333333;'>Atenciosamente,<br>Equipe Sua Empresa</p>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:8px 32px 32px 32px; font-family:Georgia, serif; font-size:14px; line-height:22px;'>
<a href='#' style='color:#7c5cff; text-decoration:underline;'>Responder este e-mail</a>
</td>
</tr>
"""

_TXT_9 = """Ola, {{ nome }},

Escrevo para compartilhar algumas novidades importantes sobre a Sua Empresa. Preferimos manter este contato simples e direto, sem enfeites, para ir direto ao que interessa.

Nos ultimos meses, temos trabalhado para melhorar a experiencia de quem confia no nosso trabalho, incluindo a equipe da {{ empresa }}. Ainda ha muito por vir, e voce vai acompanhar tudo por aqui.

Se quiser conversar, e so responder este e-mail. Temos o maior prazer em ouvir voce.

Atenciosamente,
Equipe Sua Empresa
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# 10. Cupom
# ---------------------------------------------------------------------------

_BODY_10 = """<tr>
<td class='mobile-padding' style='padding:36px 32px 8px 32px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 16px 0; font-size:22px; line-height:28px; font-weight:bold; color:#1f2130;'>{{ nome }}, aqui esta o seu cupom exclusivo</p>
<p style='margin:0 0 16px 0; font-size:15px; line-height:24px; color:#51525c;'>Use o codigo abaixo no checkout e garanta um desconto especial na sua proxima compra na Sua Empresa.</p>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:8px 32px 16px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0' style='border:2px dashed #7c5cff; border-radius:8px; background-color:#f7f7fb;'>
<tr>
<td align='center' style='padding:20px 40px; font-family:Arial, Helvetica, sans-serif;'>
<p style='margin:0 0 4px 0; font-size:12px; letter-spacing:1px; color:#8a8a99; text-transform:uppercase;'>Seu codigo</p>
<p style='margin:0; font-size:28px; line-height:32px; font-weight:bold; letter-spacing:2px; color:#7c5cff;'>BEMVINDO15</p>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' align='center' style='padding:0 32px 8px 32px;'>
<table role='presentation' cellpadding='0' cellspacing='0' border='0'>
<tr>
<td align='center' bgcolor='#7c5cff' style='background-color:#7c5cff; border-radius:6px;'>
<a href='#' style='display:inline-block; padding:14px 32px; font-family:Arial, Helvetica, sans-serif; font-size:15px; font-weight:bold; color:#ffffff; text-decoration:none; border-radius:6px;'>Usar cupom agora</a>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td class='mobile-padding' style='padding:16px 32px 32px 32px; font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:18px; color:#8a8a99;'>
Cupom valido por 15 dias a partir do recebimento deste e-mail. Nao cumulativo com outras promocoes.
</td>
</tr>
"""

_TXT_10 = """{{ nome }}, aqui esta o seu cupom exclusivo

Use o codigo abaixo no checkout e garanta um desconto especial na sua proxima compra na Sua Empresa.

Seu codigo: BEMVINDO15

Usar cupom agora: [link]

Cupom valido por 15 dias a partir do recebimento deste e-mail. Nao cumulativo com outras promocoes.
""" + _TXT_FOOTER

# ---------------------------------------------------------------------------
# Catalogo final: exatamente 10 templates, um por categoria.
# ---------------------------------------------------------------------------

TEMPLATES_PRONTOS = [
    {
        "nome": "Boas-vindas ao Clube",
        "descricao": "E-mail de boas-vindas para novos contatos que acabaram de se inscrever.",
        "categoria": "boas_vindas",
        "corpo_html": _HEAD + _BODY_1 + _FOOT,
        "corpo_texto": _TXT_1,
    },
    {
        "nome": "Newsletter Mensal",
        "descricao": "Newsletter com destaques e artigos do mes, em formato de secoes.",
        "categoria": "newsletter",
        "corpo_html": _HEAD + _BODY_2 + _FOOT,
        "corpo_texto": _TXT_2,
    },
    {
        "nome": "Promocao Relampago",
        "descricao": "E-mail de promocao com desconto em destaque e botao de call-to-action.",
        "categoria": "promocao",
        "corpo_html": _HEAD + _BODY_3 + _FOOT,
        "corpo_texto": _TXT_3,
    },
    {
        "nome": "Lancamento de Novidade",
        "descricao": "Anuncio de um novo recurso, produto ou funcionalidade.",
        "categoria": "anuncio",
        "corpo_html": _HEAD + _BODY_4 + _FOOT,
        "corpo_texto": _TXT_4,
    },
    {
        "nome": "Convite para Evento",
        "descricao": "Convite para evento com data, horario, local e botao de inscricao.",
        "categoria": "evento",
        "corpo_html": _HEAD + _BODY_5 + _FOOT,
        "corpo_texto": _TXT_5,
    },
    {
        "nome": "Follow-up Pos-contato",
        "descricao": "Mensagem de acompanhamento apos um contato, venda ou atendimento anterior.",
        "categoria": "followup",
        "corpo_html": _HEAD + _BODY_6 + _FOOT,
        "corpo_texto": _TXT_6,
    },
    {
        "nome": "Sentimos sua Falta",
        "descricao": "E-mail de reengajamento para contatos inativos, com incentivo para voltar.",
        "categoria": "reengajamento",
        "corpo_html": _HEAD + _BODY_7 + _FOOT,
        "corpo_texto": _TXT_7,
    },
    {
        "nome": "Confirmacao de Pedido",
        "descricao": "E-mail transacional confirmando um pedido ou cadastro realizado.",
        "categoria": "transacional",
        "corpo_html": _HEAD + _BODY_8 + _FOOT,
        "corpo_texto": _TXT_8,
    },
    {
        "nome": "Carta Simples",
        "descricao": "Mensagem em formato de carta, com texto limpo e pouca estilizacao.",
        "categoria": "simples",
        "corpo_html": _HEAD_SIMPLES + _BODY_9 + _FOOT,
        "corpo_texto": _TXT_9,
    },
    {
        "nome": "Cupom de Desconto Exclusivo",
        "descricao": "Oferta com codigo de cupom estilizado e destacado no corpo do e-mail.",
        "categoria": "cupom",
        "corpo_html": _HEAD + _BODY_10 + _FOOT,
        "corpo_texto": _TXT_10,
    },
]

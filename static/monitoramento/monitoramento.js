/* =========================================================================
   modulos — Módulo Monitoramento (coleta assíncrona + auto-refresh leve).
   Sem dependências externas (CSP: 'self'). Degrada com elegância: sem JS, os
   formulários "Coletar" continuam funcionando via POST normal com CSRF.

   1) Intercepta os formulários [data-mon-coletar] e envia a coleta por fetch
      (lendo o token do cookie "csrftoken" e marcando X-Requested-With). Ao
      concluir, recarrega a página para refletir status e métricas.
   2) Auto-refresh leve da lista ([data-mon-grade]): recarrega a cada 60s para
      manter os medidores atualizados. É opcional e só roda com JS.
   ========================================================================= */
(function () {
  "use strict";

  var INTERVALO_AUTO_REFRESH = 60000; // ms

  /* Sessão expirada por inatividade: o servidor responde 401 com
     {"erro":"sessao_expirada","login": url}. Redireciona para o login (só
     caminhos relativos da própria origem). Retorna true se redirecionou. */
  function tratarSessaoExpirada(resposta) {
    if (!resposta || resposta.status !== 401) { return Promise.resolve(false); }
    return resposta.json().then(function (dados) {
      var destino = dados && dados.erro === "sessao_expirada" ? String(dados.login || "") : "";
      if (destino.charAt(0) === "/" && destino.charAt(1) !== "/" && destino.charAt(1) !== "\\") {
        window.location.href = destino;
        return true;
      }
      return false;
    }).catch(function () { return false; });
  }

  function aoCarregar(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  /* Lê um cookie pelo nome (usado para o token CSRF). */
  function lerCookie(nome) {
    var casado = document.cookie.match("(^|;)\\s*" + nome + "\\s*=\\s*([^;]+)");
    return casado ? decodeURIComponent(casado.pop()) : "";
  }

  /* Coleta assíncrona: intercepta os formulários marcados. */
  function iniciarColeta() {
    if (!window.fetch) { return; } // sem fetch: os POSTs normais seguem valendo

    var formularios = document.querySelectorAll("form[data-mon-coletar]");
    formularios.forEach(function (form) {
      form.addEventListener("submit", function (evento) {
        evento.preventDefault();

        var botao = form.querySelector("button[type='submit']");
        if (botao) {
          botao.disabled = true;
          botao.classList.add("mon-coletando");
        }

        fetch(form.action, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": lerCookie("csrftoken"),
            "X-Requested-With": "XMLHttpRequest"
          },
          body: new URLSearchParams(new FormData(form))
        })
          .then(function (resposta) {
            return tratarSessaoExpirada(resposta);
          })
          .then(function (redirecionou) {
            if (redirecionou) { return; }
            // Recarrega para refletir status, medidores e histórico de forma
            // consistente (independente de sucesso/falha da coleta em si).
            window.location.reload();
          })
          .catch(function () {
            // Falha de rede do próprio fetch: tenta o envio normal do form.
            if (botao) { botao.disabled = false; botao.classList.remove("mon-coletando"); }
            form.submit();
          });
      });
    });
  }

  /* Confirmação antes de enviar (compatível com a CSP — sem onsubmit inline).
     Uso: <form ... data-confirmar="Mensagem?">. Sem JS, o form envia direto. */
  function iniciarConfirmacao() {
    var formularios = document.querySelectorAll("form[data-confirmar]");
    formularios.forEach(function (form) {
      form.addEventListener("submit", function (evento) {
        var mensagem = form.getAttribute("data-confirmar") || "Confirmar?";
        if (!window.confirm(mensagem)) {
          evento.preventDefault();
        }
      });
    });
  }

  /* Auto-refresh leve: só na lista (grade de servidores). */
  function iniciarAutoRefresh() {
    var grade = document.querySelector("[data-mon-grade]");
    if (!grade) { return; }
    window.setTimeout(function () {
      window.location.reload();
    }, INTERVALO_AUTO_REFRESH);
  }

  aoCarregar(function () {
    iniciarColeta();
    iniciarConfirmacao();
    iniciarAutoRefresh();
  });
})();

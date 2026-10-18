/* =========================================================================
   modulos — Módulo Marketing por E-mail (adendo 3 — MÓDULO 5).
   Sem dependências externas (CSP: script-src 'self'). Degrada com elegância:
   sem JS, os formulários continuam funcionando (POST normal com CSRF) e todos
   os campos SMTP permanecem visíveis.

   1) Confirmação antes de enviar: intercepta form[data-confirmar] (igual ao
      monitoramento.js) — sem onsubmit inline.
   2) Toggle dos campos SMTP: mostra/oculta o bloco [data-campos-smtp] conforme
      o valor do seletor [data-tipo-envio] (SMTP x Console).
   ========================================================================= */
(function () {
  "use strict";

  function aoCarregar(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
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

  /* Mostra/oculta os campos de SMTP conforme o tipo escolhido. Sem JS, o bloco
     fica visível e o backend valida (host obrigatório no tipo SMTP). */
  function iniciarToggleSMTP() {
    var seletor = document.querySelector("[data-tipo-envio]");
    var bloco = document.querySelector("[data-campos-smtp]");
    if (!seletor || !bloco) { return; }

    function atualizar() {
      var ehSmtp = seletor.value === "smtp";
      bloco.hidden = !ehSmtp;
    }

    seletor.addEventListener("change", atualizar);
    atualizar();
  }

  aoCarregar(function () {
    iniciarConfirmacao();
    iniciarToggleSMTP();
  });
})();

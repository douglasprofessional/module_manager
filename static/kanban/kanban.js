/* =========================================================================
   modulos — Módulo Kanban (arrastar-e-soltar OPCIONAL).
   Sem dependências externas (CSP: 'self'). Degrada com elegância: sem JS, os
   botões ◀ ▶ (mover) e "Concluir" já funcionam via POST com CSRF.

   O JS apenas ACRESCENTA arrastar-e-soltar: ao soltar um cartão em outra coluna,
   envia um POST assíncrono para ``kanban:mover_cartao`` (lendo o token do cookie
   ``csrftoken`` e marcando ``X-Requested-With``). Em caso de sucesso, recarrega
   o board para refletir ordem, contadores e botões de forma consistente.
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

  /* Lê um cookie pelo nome (usado para o token CSRF). */
  function lerCookie(nome) {
    var casado = document.cookie.match("(^|;)\\s*" + nome + "\\s*=\\s*([^;]+)");
    return casado ? decodeURIComponent(casado.pop()) : "";
  }

  function iniciarArrastar() {
    var board = document.querySelector("[data-kanban-board]");
    if (!board) { return; }

    var cartoes = board.querySelectorAll(".kanban-cartao[draggable='true']");
    var listas = board.querySelectorAll("[data-coluna-lista]");
    if (!cartoes.length || !listas.length) { return; }

    var arrastado = null; // elemento .kanban-cartao em arraste

    cartoes.forEach(function (cartao) {
      cartao.addEventListener("dragstart", function () {
        arrastado = cartao;
        cartao.classList.add("kanban-arrastando");
      });
      cartao.addEventListener("dragend", function () {
        cartao.classList.remove("kanban-arrastando");
        listas.forEach(function (l) { l.classList.remove("kanban-alvo"); });
        arrastado = null;
      });
    });

    listas.forEach(function (lista) {
      lista.addEventListener("dragover", function (evento) {
        if (!arrastado) { return; }
        evento.preventDefault(); // habilita o "drop"
        lista.classList.add("kanban-alvo");
      });
      lista.addEventListener("dragleave", function () {
        lista.classList.remove("kanban-alvo");
      });
      lista.addEventListener("drop", function (evento) {
        evento.preventDefault();
        lista.classList.remove("kanban-alvo");
        if (!arrastado) { return; }

        var coluna = lista.closest(".kanban-coluna");
        var colunaOrigem = arrastado.closest(".kanban-coluna");
        if (!coluna || coluna === colunaOrigem) { return; } // mesma coluna: nada a fazer

        var destinoId = coluna.getAttribute("data-coluna-id");
        var url = arrastado.getAttribute("data-mover-url");
        if (!destinoId || !url) { return; }

        moverCartao(url, destinoId);
      });
    });
  }

  /* Envia o POST assíncrono de movimentação e recarrega em caso de sucesso. */
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

  function moverCartao(url, destinoId) {
    var corpo = new URLSearchParams();
    corpo.append("coluna_destino", destinoId);

    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": lerCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: corpo
    })
      .then(function (resposta) {
        return tratarSessaoExpirada(resposta).then(function (redirecionou) {
          if (redirecionou) { return null; }
          if (!resposta.ok) { throw new Error("HTTP " + resposta.status); }
          return resposta.json();
        });
      })
      .then(function (dados) {
        if (dados && dados.ok) {
          window.location.reload();
        }
      })
      .catch(function (erro) {
        // Falha silenciosa: o cartão permanece; os botões ◀ ▶ seguem disponíveis.
        if (window.console && console.warn) {
          console.warn("Kanban: não foi possível mover o cartão.", erro);
        }
      });
  }

  aoCarregar(iniciarArrastar);
})();

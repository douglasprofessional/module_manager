/* =========================================================================
   modulos — interações do layout (sem dependências externas; CSP: 'self').
   Responsabilidades:
     1. Menu lateral no mobile (abrir/fechar, overlay, acessibilidade).
     2. Donut de "Oportunidades": posiciona cada fatia pelo pct acumulado.
     3. Espelha o <h1> da página no document.title (ver base.html).
     4. Fallback de realce do item de menu ativo pela URL atual.
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

  /* ----------------------------------------------------- Menu (mobile) */
  function iniciarMenu() {
    var corpo = document.body; // possui a classe .app
    var overlay = document.querySelector(".overlay-menu");
    var abridores = document.querySelectorAll("[data-abrir-menu]");
    var fechadores = document.querySelectorAll("[data-fechar-menu]");

    function ariaExpandido(valor) {
      abridores.forEach(function (b) {
        b.setAttribute("aria-expanded", valor ? "true" : "false");
      });
    }

    function abrir() {
      corpo.classList.add("menu-aberto");
      if (overlay) { overlay.hidden = false; }
      ariaExpandido(true);
    }

    function fechar() {
      corpo.classList.remove("menu-aberto");
      if (overlay) { overlay.hidden = true; }
      ariaExpandido(false);
    }

    abridores.forEach(function (b) { b.addEventListener("click", abrir); });
    fechadores.forEach(function (b) { b.addEventListener("click", fechar); });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { fechar(); }
    });

    // Ao voltar para desktop, garante estado limpo.
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900) { fechar(); }
    });
  }

  /* ----------------------------------------------------------- Donut */
  function iniciarDonut() {
    var fatias = document.querySelectorAll(".donut__fatia");
    if (!fatias.length) { return; }
    var acumulado = 0;
    fatias.forEach(function (fatia) {
      var pct = parseFloat(fatia.getAttribute("data-pct")) || 0;
      // Gira cada fatia para o seu ângulo inicial (0% = topo, por isso -90).
      var angulo = (acumulado / 100) * 360 - 90;
      fatia.setAttribute("transform", "rotate(" + angulo + " 21 21)");
      acumulado += pct;
    });
  }

  /* --------------------------------------------- Título do documento */
  function espelharTitulo() {
    var h1 = document.querySelector("[data-titulo-pagina]");
    if (!h1) { return; }
    var texto = (h1.textContent || "").trim();
    if (!texto) { return; }
    var site = document.body.getAttribute("data-site") || "modulos";
    document.title = texto + " · " + site;
  }

  /* --------------------------------- Fallback do item de menu ativo */
  function realcarItemAtivo() {
    if (document.querySelector(".menu__item--ativo")) { return; }
    var caminho = window.location.pathname;
    document.querySelectorAll(".menu__item").forEach(function (item) {
      var href = item.getAttribute("href");
      if (!href || href === "#") { return; }
      if (href === "/") {
        if (caminho === "/") { item.classList.add("menu__item--ativo"); }
      } else if (caminho.indexOf(href) === 0) {
        item.classList.add("menu__item--ativo");
      }
    });
  }

  /* ------------------------------------- Logout por inatividade */
  // Após N segundos sem navegar (data-inatividade no <body>), leva o usuário à
  // tela de login. O servidor (InatividadeSessaoMiddleware) encerra a sessão.
  function iniciarInatividade() {
    var corpo = document.body;
    var segundos = parseInt(corpo.getAttribute("data-inatividade"), 10);
    var urlLogin = corpo.getAttribute("data-url-login");
    if (!segundos || segundos <= 0 || !urlLogin || urlLogin === "#") { return; }
    var limite = Date.now() + segundos * 1000 + 5000;

    function verificar() {
      if (Date.now() >= limite) {
        window.location.assign(urlLogin);
      }
    }

    // setInterval + checagem por relógio: robusto a abas suspensas.
    window.setInterval(verificar, 15000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { verificar(); }
    });
    // Página restaurada do bfcache: revalida no servidor.
    window.addEventListener("pageshow", function (e) {
      if (e.persisted) { window.location.reload(); }
    });
  }

  aoCarregar(function () {
    iniciarInatividade();
    iniciarMenu();
    iniciarDonut();
    espelharTitulo();
    realcarItemAtivo();
  });
})();

(function () {
  function syncAuthTabs(mode) {
    var safeMode = mode === "login" ? "login" : "register";
    var tabs = document.querySelectorAll("[data-auth-mode-trigger]");
    var panes = document.querySelectorAll("[data-auth-pane]");
    tabs.forEach(function (tab) {
      var isActive = tab.getAttribute("data-auth-mode-trigger") === safeMode;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    });
    panes.forEach(function (pane) {
      var isActive = pane.getAttribute("data-auth-pane") === safeMode;
      pane.classList.toggle("is-active", isActive);
      if (isActive) {
        pane.removeAttribute("hidden");
      } else {
        pane.setAttribute("hidden", "hidden");
      }
    });
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-auth-mode-trigger]");
    if (!trigger) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    var mode = trigger.getAttribute("data-auth-mode-trigger");
    syncAuthTabs(mode);
    try {
      var nextUrl = new URL(trigger.href, window.location.origin);
      window.history.replaceState({}, "", nextUrl.toString());
    } catch (_err) {
      window.location.hash = "register-form-card";
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var active = document.querySelector("[data-auth-mode-trigger].is-active");
    syncAuthTabs(active ? active.getAttribute("data-auth-mode-trigger") : "register");
  });
})();

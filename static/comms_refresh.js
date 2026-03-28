(function () {
  var root = document.querySelector("[data-comms-auto-refresh='1']");
  if (!root) {
    return;
  }
  var delayMs = parseInt(root.getAttribute("data-auto-refresh-ms") || "0", 10);
  if (!delayMs || delayMs < 1000) {
    return;
  }

  function shouldPauseRefresh() {
    if (document.hidden) {
      return true;
    }
    var compose = root.querySelector("[data-comms-compose='1']");
    if (!compose) {
      return false;
    }
    var field = compose.querySelector("input[name='message'], textarea[name='message']");
    if (!field) {
      return false;
    }
    return document.activeElement === field && field.value.trim().length > 0;
  }

  function schedule() {
    window.setTimeout(function () {
      if (shouldPauseRefresh()) {
        schedule();
        return;
      }
      window.location.reload();
    }, delayMs);
  }

  schedule();
})();

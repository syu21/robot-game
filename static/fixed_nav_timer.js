(function () {
  var buttons = document.querySelectorAll(".robo-fixed-nav-explore[data-ready-at]");
  if (!buttons.length) return;

  var clientStart = Math.floor(Date.now() / 1000);
  var firstNow = parseInt(buttons[0].getAttribute("data-now") || "0", 10);

  function tick() {
    var now = firstNow > 0
      ? firstNow + (Math.floor(Date.now() / 1000) - clientStart)
      : Math.floor(Date.now() / 1000);

    buttons.forEach(function (button) {
      var readyAt = parseInt(button.getAttribute("data-ready-at") || "0", 10);
      var remain = Math.max(0, readyAt - now);
      if (remain > 0) {
        button.textContent = "出撃 " + remain + "秒";
        button.classList.remove("is-ready");
        button.classList.add("is-waiting");
        if ("disabled" in button) button.disabled = true;
      } else {
        button.textContent = "出撃OK";
        button.classList.remove("is-waiting");
        button.classList.add("is-ready");
        if ("disabled" in button) button.disabled = false;
      }
    });
  }

  tick();
  window.setInterval(tick, 1000);
})();

(function () {
  document.querySelectorAll("[data-collab-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var card = button.closest(".collab-card");
      var secretEl = card ? card.querySelector("[data-collab-secret]") : null;
      var statusEl = card ? card.querySelector("[data-collab-copy-status]") : null;
      var text = secretEl ? String(secretEl.textContent || "").trim() : "";
      if (!text) return;
      if (!navigator.clipboard || !navigator.clipboard.writeText) {
        if (statusEl) statusEl.textContent = "コピーできない場合は合言葉を選択してください。";
        return;
      }
      navigator.clipboard.writeText(text).then(
        function () {
          if (statusEl) statusEl.textContent = "コピーしました。";
        },
        function () {
          if (statusEl) statusEl.textContent = "コピーできない場合は合言葉を選択してください。";
        }
      );
    });
  });
})();

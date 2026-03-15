(() => {
  const applyBattleScope = () => {
    if (document.body) {
      document.body.classList.add("battle-page");
    }
    const scene = document.querySelector(".battle-scene.has-boss-bg[data-battle-bg-url]");
    if (!scene) return;
    const raw = scene.getAttribute("data-battle-bg-url") || "";
    const safe = raw.replace(/["'()\\]/g, "");
    if (!safe) return;
    scene.style.setProperty("--battle-bg-image", `url("${safe}")`);
  };

  const setupVictoryOverlay = () => {
    if (!window.__uiEffectsEnabled) {
      document.body.classList.remove("battle-ritual-active");
      return;
    }
    const overlay = document.getElementById("battle-ritual-overlay");
    if (!overlay) return;
    document.body.classList.add("battle-ritual-active");
    let cleaned = false;
    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      document.body.classList.remove("battle-ritual-active");
    };
    overlay.addEventListener("animationend", cleanup, { once: true });
    window.setTimeout(cleanup, 900);
    window.addEventListener("pagehide", cleanup, { once: true });
  };

  const setupExploreReturnCooldown = () => {
    const btn = document.getElementById("explore-return-btn");
    if (!btn) return;
    const isAdmin = String(btn.dataset.ctAdmin || "") === "1";
    if (isAdmin) return;
    let remain = Number(btn.dataset.ctRemain || 0);
    if (!Number.isFinite(remain)) remain = 0;
    remain = Math.max(0, Math.floor(remain));
    const label = document.getElementById("explore-return-ct-label");
    const readyLabel = String(btn.dataset.ctaReadyLabel || "もう一度出撃");

    const render = () => {
      if (remain <= 0) {
        btn.disabled = false;
        btn.textContent = readyLabel;
        if (label) {
          label.textContent = "出撃可能";
        }
        return true;
      }
      btn.disabled = true;
      btn.textContent = `もう一度出撃（あと${remain}秒）`;
      if (label) {
        label.textContent = `CT中: あと${remain}秒`;
      }
      return false;
    };

    if (render()) return;
    const timer = window.setInterval(() => {
      remain -= 1;
      if (render()) {
        window.clearInterval(timer);
      }
    }, 1000);
  };

  const init = () => {
    applyBattleScope();
    setupVictoryOverlay();
    setupExploreReturnCooldown();
  };

  document.addEventListener("DOMContentLoaded", init);
  window.addEventListener("pageshow", applyBattleScope);
})();

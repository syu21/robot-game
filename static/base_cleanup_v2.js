(() => {
  const diag = window.__clientDiag || null;
  const markStep = (step, extra) => {
    try {
      if (diag && typeof diag.step === "function") {
        diag.step(step, extra || null);
      }
    } catch (_err) {
      // no-op
    }
  };
  markStep("base_cleanup:start");

  const body = document.body;
  const uiEnabled = !!(body && body.dataset && body.dataset.uiEffectsEnabled === "1");
  window.__uiEffectsEnabled = uiEnabled;

  const cleanupBattleRitual = () => {
    const overlay = document.getElementById("battle-ritual-overlay");
    if (overlay) {
      overlay.remove();
    }
    if (document.body) {
      document.body.classList.remove("battle-ritual-active", "battle-page");
    }
  };

  const cleanupImageOverlay = () => {
    const overlaySelectors = [
      "#image-viewer-overlay",
      "#image-modal",
      "#lightbox-overlay",
      ".image-viewer-overlay",
      ".image-modal-overlay",
      ".lightbox-overlay",
      ".lightbox-backdrop",
      ".modal-backdrop.image-backdrop",
      "[data-image-overlay='1']",
    ];

    overlaySelectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => node.remove());
    });

    if (document.body) {
      document.body.classList.remove("image-viewer-open", "modal-open", "lightbox-open");
    }
  };

  window.__cleanupBattleRitual = cleanupBattleRitual;
  window.__cleanupImageOverlay = cleanupImageOverlay;

  const cleanupAll = () => {
    cleanupBattleRitual();
    cleanupImageOverlay();
  };

  document.addEventListener("DOMContentLoaded", cleanupAll);
  window.addEventListener("pageshow", cleanupAll);

  if (window.htmx && document.body) {
    document.body.addEventListener("htmx:beforeSwap", cleanupAll);
    document.body.addEventListener("htmx:afterSwap", cleanupAll);
  }
  markStep("base_cleanup:done");
})();

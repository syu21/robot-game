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

  const init = () => {
    markStep("robots:init:start");
    const root = document.getElementById("robot-list-root");
    if (!root) {
      markStep("robots:init:skip-no-root");
      return;
    }
    markStep("robots:init:list-found", {
      card_count: root.querySelectorAll(".robot-card").length,
    });
    markStep("robots:init:done");
  };

  document.addEventListener("DOMContentLoaded", init);
})();

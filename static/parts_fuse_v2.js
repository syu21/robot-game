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
  const reportCaught = (step, err) => {
    try {
      if (diag && typeof diag.error === "function") {
        diag.error("caught_exception", {
          message: err && err.message ? err.message : String(err || "caught_exception"),
          source: "static/parts_fuse_v2.js",
          line: 0,
          column: 0,
          stack: err && err.stack ? err.stack : "",
          last_step: step,
        });
      }
    } catch (_err) {
      // no-op
    }
  };

  markStep("parts_fuse:init:start");
  const onStrengthenPage =
    document.body &&
    document.body.classList &&
    (document.body.classList.contains("parts-fuse-page") ||
      document.body.classList.contains("parts-strengthen-page"));
  const root = document.getElementById("parts-fuse-root");
  if (!onStrengthenPage && !root) {
    markStep("parts_fuse:init:skip-not-page");
    return;
  }
  markStep("parts_fuse:init:root-found");

  const panel = document.getElementById("fuse-select-panel");
  if (!panel) {
    markStep("parts_fuse:init:panel-missing");
    return;
  }
  markStep("parts_fuse:init:panel-found");
  const scrollKey = "parts_strengthen_scroll_y";

  const stackRadios = Array.from(panel.querySelectorAll("input.fuse-base-radio"));
  const selectedCountEl = document.getElementById("fuse-selected-count");
  const submitBtn = document.getElementById("fuse-select-submit");
  const baseSelectedEl = document.getElementById("fuse-base-selected");
  const materialSelectedEl = document.getElementById("fuse-material-selected");
  const resultExpectedEl = document.getElementById("fuse-result-expected");

  if (
    stackRadios.length === 0 ||
    !selectedCountEl ||
    !submitBtn ||
    !baseSelectedEl ||
    !materialSelectedEl ||
    !resultExpectedEl
  ) {
    return;
  }

  function selectedStack() {
    return stackRadios.find((r) => r.checked) || null;
  }

  function syncState() {
    const stack = selectedStack();
    if (!stack) {
      selectedCountEl.textContent = "0";
      baseSelectedEl.textContent = "未選択";
      materialSelectedEl.textContent = "同じパーツの所持中2個を使います";
      resultExpectedEl.textContent = "+1固定";
      submitBtn.disabled = true;
      return;
    }

    selectedCountEl.textContent = "1";
    baseSelectedEl.textContent = String(stack.dataset.partLabel || "未選択");
    materialSelectedEl.textContent = String(stack.dataset.materialLabels || "同じパーツの所持中2個を使います");
    const partLabel = String(stack.dataset.partLabel || "パーツ");
    const basePlus = Number(stack.dataset.basePlus || 0);
    const inc = 1;
    resultExpectedEl.textContent = `${partLabel} +${basePlus} → +${basePlus + inc}（+1固定）`;
    submitBtn.disabled = false;
  }

  // Keep continuous strengthen UX stable: return to previous viewport after redirect.
  try {
    const raw = window.sessionStorage.getItem(scrollKey);
    if (raw !== null) {
      const y = Number(raw);
      if (Number.isFinite(y) && y >= 0) {
        window.scrollTo(0, y);
      }
      window.sessionStorage.removeItem(scrollKey);
    }
  } catch (_err) {
    reportCaught("parts_fuse:init:restore-scroll", _err);
  }

  panel.addEventListener("submit", () => {
    try {
      window.sessionStorage.setItem(scrollKey, String(window.scrollY || 0));
    } catch (_err) {
      // no-op
    }
  });

  stackRadios.forEach((radio) => {
    radio.addEventListener("change", syncState);
  });
  try {
    syncState();
    markStep("parts_fuse:init:done");
  } catch (err) {
    reportCaught("parts_fuse:init:sync-state", err);
  }
})();

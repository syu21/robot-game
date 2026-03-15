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
          source: "static/parts_fuse.js",
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

  const stackRadios = Array.from(panel.querySelectorAll("input.fuse-stack-radio"));
  const selectedCountEl = document.getElementById("fuse-selected-count");
  const submitBtn = document.getElementById("fuse-select-submit");
  const baseIdInput = document.getElementById("fuse-base-id");
  const baseSelectedEl = document.getElementById("fuse-base-selected");
  const materialSelectedEl = document.getElementById("fuse-material-selected");
  const resultExpectedEl = document.getElementById("fuse-result-expected");

  if (
    stackRadios.length === 0 ||
    !selectedCountEl ||
    !submitBtn ||
    !baseIdInput ||
    !baseSelectedEl ||
    !materialSelectedEl ||
    !resultExpectedEl
  ) {
    return;
  }

  function parseOptions(raw) {
    try {
      const data = JSON.parse(raw || "[]");
      return Array.isArray(data) ? data : [];
    } catch (_err) {
      return [];
    }
  }

  function selectedStack() {
    return stackRadios.find((r) => r.checked) || null;
  }

  function syncState() {
    const stack = selectedStack();
    if (!stack) {
      selectedCountEl.textContent = "0";
      baseSelectedEl.textContent = "未選択";
      materialSelectedEl.textContent = "自動選択（2個・低+優先）";
      resultExpectedEl.textContent = "+1固定";
      submitBtn.disabled = true;
      baseIdInput.value = "";
      return;
    }

    const options = parseOptions(stack.dataset.instanceOptions);
    const base = options.length > 0 ? options[0] : null;
    const materials = options
      .filter((opt) => {
        if (base && Number(opt.id) === Number(base.id)) return false;
        return String(opt.status || "inventory").toLowerCase() === "inventory";
      })
      .sort((a, b) => {
        const plusA = Number(a.plus || 0);
        const plusB = Number(b.plus || 0);
        if (plusA !== plusB) return plusA - plusB;
        return Number(a.id || 0) - Number(b.id || 0);
      })
      .slice(0, 2);
    selectedCountEl.textContent = "1";
    baseSelectedEl.textContent = base ? String(base.label || `#${base.id}`) : "未選択";
    materialSelectedEl.textContent =
      materials.length === 2
        ? materials.map((m) => String(m.label || `#${m.id}`)).join(", ")
        : "在庫素材が不足";
    const partLabel = String(stack.dataset.partLabel || "パーツ");
    const basePlus = Number(base && base.plus ? base.plus : 0);
    const inc = 1;
    resultExpectedEl.textContent = `${partLabel} +${basePlus} → +${basePlus + inc}（+1固定）`;

    baseIdInput.value = base ? String(base.id) : "";
    submitBtn.disabled = !(base && materials.length === 2);
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

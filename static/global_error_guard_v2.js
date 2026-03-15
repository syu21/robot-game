(() => {
  const ERROR_ENDPOINT = "/client-error/js";
  let toastShown = false;
  const body = document.body;
  const debugDiag = !!(body && body.dataset && body.dataset.jsDiag === "1");
  let lastStep = "";

  function detectPageName() {
    const dataPage = body && body.dataset ? String(body.dataset.pageName || "") : "";
    if (dataPage) {
      if (dataPage === "home") return "home";
      if (dataPage.startsWith("parts")) return "parts";
      if (dataPage === "robots" || dataPage.startsWith("robot_")) return "robots";
      if (dataPage === "explore" || dataPage.startsWith("battle")) return "battle";
    }
    if (body && body.classList) {
      if (body.classList.contains("home-page")) return "home";
      if (body.classList.contains("parts-page")) return "parts";
      if (body.classList.contains("parts-fuse-page") || body.classList.contains("parts-strengthen-page")) return "parts_strengthen";
      if (body.classList.contains("robots-page")) return "robots";
      if (body.classList.contains("battle-page")) return "battle";
    }
    const path = String(window.location.pathname || "");
    if (path.startsWith("/parts/strengthen") || path.startsWith("/parts/fuse")) return "parts_strengthen";
    if (path.startsWith("/robots")) return "robots";
    if (path.startsWith("/home")) return "home";
    if (path.startsWith("/explore") || path.startsWith("/battle")) return "battle";
    return "unknown";
  }

  function collectImportantDomState() {
    return {
      home_ct_status: !!document.getElementById("home-ct-status"),
      parts_fuse_root: !!document.getElementById("parts-fuse-root"),
      robot_list_root: !!document.getElementById("robot-list-root"),
      explore_area_select: !!document.getElementById("explore-area-select"),
    };
  }

  function collectScriptNames() {
    try {
      return Array.from(document.querySelectorAll("script[src]"))
        .map((el) => {
          const src = String(el.getAttribute("src") || "");
          if (!src) return "";
          const noQuery = src.split("?")[0];
          return noQuery.split("/").pop() || noQuery;
        })
        .filter(Boolean)
        .slice(0, 20);
    } catch (_err) {
      return [];
    }
  }

  function postError(payload) {
    const data = {
      page_name: String(payload.page_name || detectPageName()),
      pathname: String(payload.pathname || window.location.pathname || ""),
      full_url: String(payload.full_url || window.location.href || ""),
      kind: String(payload.kind || "window.onerror"),
      message: String(payload.message || ""),
      source: String(payload.source || ""),
      line: Number(payload.line || 0),
      column: Number(payload.column || 0),
      stack: String(payload.stack || ""),
      url: String(window.location.href || ""),
      userAgent: String(navigator.userAgent || ""),
      requestId: String(window.__requestId || ""),
      body_class: String((document.body && document.body.className) || ""),
      body_id: String((document.body && document.body.id) || ""),
      page_template: String(
        (document.body && document.body.dataset && document.body.dataset.pageTemplate) ||
          (document.body && document.body.dataset && document.body.dataset.pageName) ||
          ""
      ),
      ready_state: String(document.readyState || ""),
      last_step: String(payload.last_step || lastStep || window.__lastClientInitStep || ""),
      important_dom_state: payload.important_dom_state || collectImportantDomState(),
      loaded_scripts: payload.loaded_scripts || collectScriptNames(),
      step: String(payload.step || ""),
      extra: payload.extra || null,
    };
    const body = JSON.stringify(data);
    try {
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon(ERROR_ENDPOINT, blob);
        return;
      }
    } catch (_err) {
      // Fallback fetch below.
    }
    fetch(ERROR_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
      credentials: "same-origin",
    }).catch(() => {});
  }

  function showNonBlockingToast() {
    if (toastShown) return;
    toastShown = true;
    try {
      const toast = document.createElement("div");
      toast.className = "client-error-toast";
      toast.textContent = "表示エラーを検出しました。再読み込みを試してください。";
      Object.assign(toast.style, {
        position: "fixed",
        right: "12px",
        bottom: "12px",
        zIndex: "9999",
        background: "rgba(28, 28, 30, 0.94)",
        color: "#fff",
        padding: "10px 12px",
        borderRadius: "8px",
        fontSize: "13px",
        maxWidth: "280px",
        boxShadow: "0 6px 20px rgba(0,0,0,0.25)",
      });
      document.body.appendChild(toast);
      window.setTimeout(() => {
        toast.remove();
      }, 3200);
    } catch (_err) {
      // no-op
    }
  }

  function handleError(kind, detail) {
    console.error("[client-error]", kind, detail);
    postError({
      kind,
      message: detail && detail.message ? detail.message : String(detail || ""),
      source: detail && detail.source ? detail.source : "",
      line: detail && detail.line ? detail.line : 0,
      column: detail && detail.column ? detail.column : 0,
      stack: detail && detail.stack ? detail.stack : "",
      last_step: detail && detail.last_step ? detail.last_step : lastStep,
    });
    if (!debugDiag) {
      showNonBlockingToast();
    }
  }

  function trackStep(step, extra) {
    if (!step) return;
    lastStep = String(step);
    window.__lastClientInitStep = lastStep;
    console.info("[client-step]", lastStep, extra || {});
    postError({
      kind: "init_step",
      message: "client_init_step",
      step: lastStep,
      last_step: lastStep,
      extra: extra || null,
    });
  }

  function runOverlayScan(kindLabel) {
    try {
      const ww = Math.max(1, window.innerWidth || document.documentElement.clientWidth || 1);
      const hh = Math.max(1, window.innerHeight || document.documentElement.clientHeight || 1);
      document.querySelectorAll("*").forEach((el) => {
        const style = window.getComputedStyle(el);
        if (style.position !== "fixed" && style.position !== "absolute") return;
        const rect = el.getBoundingClientRect();
        if (rect.width < ww * 0.5 && rect.height < hh * 0.4) return;
        postError({
          kind: "overlay-scan",
          message: "large_fixed_or_absolute_element",
          step: kindLabel,
          extra: {
            tag: el.tagName,
            id: el.id || "",
            className: el.className || "",
            rect: {
              x: Math.round(rect.x),
              y: Math.round(rect.y),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
            },
            zIndex: style.zIndex || "",
            backgroundColor: style.backgroundColor || "",
          },
        });
      });
    } catch (_err) {
      // no-op
    }
  }

  function installMutationObserverRunawayGuard() {
    if (!debugDiag || !window.MutationObserver || window.__MO_DIAG_INSTALLED__) return;
    window.__MO_DIAG_INSTALLED__ = true;
    const NativeMO = window.MutationObserver;
    let callbackCount = 0;
    window.MutationObserver = function MutationObserverProxy(cb) {
      return new NativeMO((mutations, obs) => {
        callbackCount += 1;
        if (callbackCount > 200) {
          postError({
            kind: "MO-runaway",
            message: "mutationobserver_callback_overflow",
            last_step: window.__lastClientInitStep || "",
            extra: { callback_count: callbackCount, mutation_count: mutations ? mutations.length : 0 },
          });
          try {
            obs.disconnect();
          } catch (_e) {
            // no-op
          }
          callbackCount = 0;
          return;
        }
        cb(mutations, obs);
      });
    };
  }

  window.__clientDiag = {
    post: postError,
    error: handleError,
    step: trackStep,
    setStep: (step) => {
      if (!step) return;
      lastStep = String(step);
      window.__lastClientInitStep = lastStep;
    },
  };

  window.onerror = function onWindowError(message, source, line, column, error) {
    handleError("window.onerror", {
      message,
      source,
      line,
      column,
      stack: error && error.stack ? error.stack : "",
    });
    return false;
  };

  window.onunhandledrejection = function onUnhandledRejection(event) {
    const reason = event && event.reason;
    const message = reason && reason.message ? reason.message : String(reason || "Unhandled promise rejection");
    handleError("unhandledrejection", {
      message,
      source: "",
      line: 0,
      column: 0,
      stack: reason && reason.stack ? reason.stack : "",
    });
    return false;
  };

  // Guard main startup path so an init exception does not turn into a blank page.
  document.addEventListener("DOMContentLoaded", () => {
    try {
      trackStep(`${detectPageName()}:guard:dom-ready`);
      installMutationObserverRunawayGuard();
      if (debugDiag) {
        runOverlayScan("dom-ready");
        window.addEventListener(
          "scroll",
          () => {
            runOverlayScan("first-scroll");
          },
          { once: true, passive: true }
        );
      }
      document.documentElement.classList.add("app-js-ready");
    } catch (err) {
      handleError("domcontentloaded.init", {
        message: err && err.message ? err.message : "DOMContentLoaded init failed",
        stack: err && err.stack ? err.stack : "",
      });
    }
  });
})();

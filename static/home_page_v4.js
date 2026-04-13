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
          source: "static/home_page_v4.js",
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

  const isHomePage = () => !!(document.body && document.body.classList.contains("home-page"));

  const syncHomeMobileClass = () => {
    if (!isHomePage()) return;
    const measured = [
      window.innerWidth || 0,
      document.documentElement ? document.documentElement.clientWidth : 0,
      window.screen ? window.screen.width : 0,
    ].filter((v) => Number.isFinite(v) && v > 0);
    if (window.visualViewport && Number.isFinite(window.visualViewport.width)) {
      measured.push(Math.floor(window.visualViewport.width));
    }
    const minWidth = measured.length ? Math.min.apply(null, measured) : 9999;
    document.body.classList.toggle("home-mobile", minWidth <= 640);
  };

  const bindCooldownView = () => {
    const ctStatus = document.getElementById("home-ct-status");
    if (!ctStatus) return;

    const isAdmin = String(ctStatus.dataset.isAdmin || "0") === "1";
    const ctaButtons = Array.from(document.querySelectorAll("[data-explore-cta='1']"));
    const ctCopies = Array.from(document.querySelectorAll("[data-home-ct-copy='1']"));
    let timerId = null;

    const formatRemain = (totalSeconds) => {
      const remain = Math.max(0, Math.floor(Number(totalSeconds) || 0));
      const minutes = Math.floor(remain / 60);
      const seconds = remain % 60;
      return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    const setReady = () => {
      ctStatus.textContent = "出撃可能！";
      ctCopies.forEach((el) => {
        el.textContent = "出撃可能";
      });
      ctaButtons.forEach((btn) => {
        btn.disabled = false;
        btn.textContent = String(btn.dataset.ctaReadyLabel || "出撃する");
      });
    };

    const setCooling = (remain) => {
      const remainLabel = formatRemain(remain);
      ctStatus.textContent = `出撃まであと ${remainLabel}`;
      ctCopies.forEach((el) => {
        el.textContent = `クールタイム中 あと ${remainLabel}`;
      });
      ctaButtons.forEach((btn) => {
        btn.disabled = true;
        btn.textContent = `あと ${remainLabel} で出撃可能`;
      });
    };

    if (isAdmin) {
      setReady();
      return;
    }

    const readyAt = Number(ctStatus.dataset.ctReadyAt || "0");
    if (!Number.isFinite(readyAt) || readyAt <= 0) {
      setReady();
      return;
    }

    const stopTicker = () => {
      if (timerId !== null) {
        window.clearInterval(timerId);
        timerId = null;
      }
    };

    const tick = () => {
      const now = Math.floor(Date.now() / 1000);
      const remain = Math.max(0, readyAt - now);
      if (remain > 0) {
        setCooling(remain);
        return false;
      } else {
        setReady();
        stopTicker();
        return true;
      }
    };

    const startTicker = () => {
      stopTicker();
      if (tick()) return;
      if (timerId === null) {
        timerId = window.setInterval(tick, 1000);
      }
    };

    startTicker();
    window.addEventListener("pageshow", startTicker);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        startTicker();
      }
    });
    window.addEventListener("pagehide", stopTicker);
  };

  const bindResearchBoostTimers = () => {
    const nodes = Array.from(document.querySelectorAll("[data-research-boost-until]"));
    if (!nodes.length) return;
    let timerId = null;

    const formatRemain = (totalSeconds) => {
      const remain = Math.max(0, Math.floor(Number(totalSeconds) || 0));
      const minutes = Math.floor(remain / 60);
      const seconds = remain % 60;
      return `${minutes}分${String(seconds).padStart(2, "0")}秒`;
    };

    const tick = () => {
      const now = Math.floor(Date.now() / 1000);
      let hasActive = false;
      nodes.forEach((node) => {
        const until = Number(node.dataset.researchBoostUntil || "0");
        const remain = Math.max(0, until - now);
        if (remain > 0) {
          hasActive = true;
          node.textContent = `残り ${formatRemain(remain)}`;
        } else {
          node.textContent = "残り 0分00秒";
        }
      });
      if (!hasActive && timerId !== null) {
        window.clearInterval(timerId);
        timerId = null;
      }
    };

    tick();
    timerId = window.setInterval(tick, 1000);
    window.addEventListener("pagehide", () => {
      if (timerId !== null) {
        window.clearInterval(timerId);
        timerId = null;
      }
    });
  };

  const bindInviteCopy = () => {
    const btn = document.getElementById("invite-copy-btn");
    if (!btn) return;

    btn.addEventListener("click", async () => {
      const targetId = btn.getAttribute("data-copy-target");
      const input = targetId ? document.getElementById(targetId) : null;
      const inlineText = btn.getAttribute("data-copy-text");
      const text = String((inlineText && inlineText.trim()) || (input && input.value) || "");
      if (!text) return;

      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "コピー済み";
        window.setTimeout(() => {
          btn.textContent = "コピー";
        }, 1200);
      } catch (_err) {
        if (input) {
          input.focus();
          input.select();
        }
      }
    });
  };

  const bindIntroModal = () => {
    const introModal = document.getElementById("intro-guide-modal");
    if (!introModal) return;

    const dismissForm = document.getElementById("intro-guide-dismiss-form");
    const noShowInput = document.getElementById("intro-guide-no-show");

    const syncNoShow = () => {
      if (!dismissForm || !noShowInput) return;
      const hidden = dismissForm.querySelector("input[name='dont_show_again']");
      if (hidden) {
        hidden.value = noShowInput.checked ? "1" : "0";
      }
    };

    const dismiss = () => {
      if (!dismissForm) return;
      syncNoShow();
      dismissForm.submit();
    };

    syncNoShow();
    if (noShowInput) {
      noShowInput.addEventListener("change", syncNoShow);
    }

    introModal.querySelectorAll("[data-intro-close='1']").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.preventDefault();
        dismiss();
      });
    });

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        dismiss();
      }
    });
  };

  const bindStarterRobotNameModal = () => {
    const modal = document.getElementById("starter-robot-name-modal");
    if (!modal) return;
    const input = document.getElementById("starter-robot-name-input");
    if (!input) return;
    window.setTimeout(() => {
      try {
        input.focus();
        input.select();
      } catch (_err) {
        // no-
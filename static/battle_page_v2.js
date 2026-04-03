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

  const setupBattleShortReplay = () => {
    const root = document.getElementById("battle-short-replay");
    const dataEl = document.getElementById("battle-short-replay-data");
    const followup = document.getElementById("battle-replay-followup");
    if (!root || !dataEl || !followup || !window.__uiEffectsEnabled) return;

    let replay;
    try {
      replay = JSON.parse(dataEl.textContent || "{}");
    } catch (_error) {
      return;
    }
    if (!replay || !Array.isArray(replay.events) || !replay.events.length) return;

    const stage = root.querySelector("[data-replay-stage]");
    const playerUnit = root.querySelector('[data-replay-unit="player"]');
    const enemyUnit = root.querySelector('[data-replay-unit="enemy"]');
    const logHost = root.querySelector("[data-replay-log]");
    const resultHost = root.querySelector("[data-replay-result]");
    const skipButton = root.querySelector("[data-replay-skip]");
    const introDelay = Number(root.dataset.introDelayMs || replay.intro_delay_ms || 120);
    const eventDuration = Number(root.dataset.eventDurationMs || replay.event_duration_ms || 380);
    const outroHold = Number(root.dataset.outroHoldMs || replay.outro_hold_ms || 340);
    let finished = false;

    const resetClasses = () => {
      root.classList.remove("is-critical", "is-heavy");
      if (stage) {
        stage.dataset.currentEvent = "";
      }
      [playerUnit, enemyUnit].forEach((node) => {
        if (!node) return;
        node.classList.remove("is-acting", "is-hit", "is-evading", "is-guarding", "is-finished");
      });
    };

    const pushLog = (label) => {
      if (!logHost || !label) return;
      const entries = Array.from(logHost.querySelectorAll(".battle-short-replay-log-line")).slice(0, 2);
      logHost.innerHTML = "";
      const nextEntries = [String(label), ...entries.map((node) => node.textContent || "").filter(Boolean)].slice(0, 3);
      nextEntries.forEach((text, index) => {
        const line = document.createElement("div");
        line.className = `battle-short-replay-log-line${index === 0 ? " is-current" : ""}`;
        line.textContent = text;
        logHost.appendChild(line);
      });
    };

    const revealFollowup = () => {
      if (finished) return;
      finished = true;
      root.hidden = true;
      resetClasses();
      document.body.classList.remove("battle-short-replay-active");
    };

    const applyEvent = (event) => {
      resetClasses();
      const type = String((event && event.type) || "");
      const actor = String((event && event.actor) || "");
      if (stage) {
        stage.dataset.currentEvent = type;
      }
      if (event && event.crit) {
        root.classList.add("is-critical");
      }
      if (event && event.heavy) {
        root.classList.add("is-heavy");
      }
      if (actor === "player" && playerUnit) {
        playerUnit.classList.add("is-acting");
      }
      if (actor === "enemy" && enemyUnit) {
        enemyUnit.classList.add("is-acting");
      }
      if (type === "player_strike" || type === "player_finisher") {
        enemyUnit && enemyUnit.classList.add("is-hit");
      } else if (type === "enemy_strike" || type === "enemy_finisher") {
        playerUnit && playerUnit.classList.add("is-hit");
      } else if (type === "enemy_miss") {
        playerUnit && playerUnit.classList.add("is-evading");
      } else if (type === "player_miss") {
        enemyUnit && enemyUnit.classList.add("is-evading");
      } else if (type === "player_guard") {
        playerUnit && playerUnit.classList.add("is-guarding");
      } else if (type === "boss_defeated") {
        enemyUnit && enemyUnit.classList.add("is-finished");
      }
      pushLog((event && event.label) || "決着！");
    };

    const run = async () => {
      root.hidden = false;
      document.body.classList.add("battle-short-replay-active");
      if (resultHost) {
        resultHost.hidden = true;
      }
      pushLog("戦闘開始");
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(60, introDelay)));
      for (const event of replay.events) {
        if (finished) return;
        applyEvent(event);
        await new Promise((resolve) => window.setTimeout(resolve, Math.max(180, eventDuration)));
      }
      if (finished) return;
      resetClasses();
      if (resultHost) {
        resultHost.hidden = false;
      }
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(180, outroHold)));
      revealFollowup();
    };

    skipButton &&
      skipButton.addEventListener("click", (event) => {
        event.preventDefault();
        revealFollowup();
      });

    run().catch(() => {
      revealFollowup();
    });
  };

  const init = () => {
    applyBattleScope();
    setupVictoryOverlay();
    setupBattleShortReplay();
    setupExploreReturnCooldown();
  };

  document.addEventListener("DOMContentLoaded", init);
  window.addEventListener("pageshow", applyBattleScope);
})();

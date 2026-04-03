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
    const captionHost = root.querySelector("[data-replay-caption]");
    const projectile = root.querySelector("[data-replay-projectile]");
    const hitflash = root.querySelector("[data-replay-hitflash]");
    const sparks = root.querySelector("[data-replay-sparks]");
    const resultHost = root.querySelector("[data-replay-result]");
    const skipButton = root.querySelector("[data-replay-skip]");
    const introDelay = Number(root.dataset.introDelayMs || replay.intro_delay_ms || 120);
    const eventDuration = Number(root.dataset.eventDurationMs || replay.event_duration_ms || 380);
    const outroHold = Number(root.dataset.outroHoldMs || replay.outro_hold_ms || 340);
    let finished = false;
    const timers = [];

    const queueTimeout = (callback, delayMs) => {
      const timerId = window.setTimeout(() => {
        const index = timers.indexOf(timerId);
        if (index >= 0) timers.splice(index, 1);
        callback();
      }, delayMs);
      timers.push(timerId);
      return timerId;
    };

    const clearTimers = () => {
      while (timers.length) {
        window.clearTimeout(timers.pop());
      }
    };

    const clearNodeClasses = (node, classNames) => {
      if (!node) return;
      classNames.forEach((className) => node.classList.remove(className));
    };

    const resetClasses = () => {
      clearTimers();
      root.classList.remove("is-critical", "is-heavy", "is-hit-stop");
      if (stage) {
        stage.dataset.currentEvent = "";
        stage.dataset.currentActor = "";
        stage.dataset.currentTarget = "";
        stage.dataset.reaction = "";
        stage.dataset.projectile = "";
      }
      [playerUnit, enemyUnit].forEach((node) => {
        if (!node) return;
        node.classList.remove("is-acting", "is-hit", "is-evading", "is-guarding", "is-finished");
      });
      clearNodeClasses(projectile, ["is-live", "from-player", "from-enemy", "to-player", "to-enemy", "is-critical", "is-heavy"]);
      clearNodeClasses(hitflash, ["is-live", "target-player", "target-enemy", "is-critical"]);
      clearNodeClasses(sparks, ["is-live", "target-player", "target-enemy", "is-critical", "is-heavy"]);
    };

    const setCaption = (label) => {
      if (!captionHost) return;
      captionHost.textContent = String(label || "決着！");
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
      const target = String((event && event.target) || "");
      const projectileType = String((event && event.projectile) || "");
      const reaction = String((event && event.reaction) || "");
      if (root) {
        void root.offsetWidth;
      }
      if (stage) {
        stage.dataset.currentEvent = type;
        stage.dataset.currentActor = actor;
        stage.dataset.currentTarget = target;
        stage.dataset.projectile = projectileType;
        stage.dataset.reaction = reaction;
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
      if (projectile && projectileType) {
        projectile.classList.add("is-live", `from-${actor}`, `to-${target}`);
        if (event && event.crit) projectile.classList.add("is-critical");
        if (event && event.heavy) projectile.classList.add("is-heavy");
      }
      if (hitflash && (reaction === "hit" || reaction === "critical" || reaction === "brace" || reaction === "finish")) {
        hitflash.classList.add("is-live", `target-${target || actor}`);
        if (event && event.crit) hitflash.classList.add("is-critical");
      }
      if (sparks && (reaction === "critical" || event.heavy || reaction === "finish")) {
        sparks.classList.add("is-live", `target-${target || actor}`);
        if (event && event.crit) sparks.classList.add("is-critical");
        if (event && event.heavy) sparks.classList.add("is-heavy");
      }
      if (event && event.crit) {
        root.classList.add("is-hit-stop");
        queueTimeout(() => {
          root.classList.remove("is-hit-stop");
        }, 120);
      }
      setCaption((event && event.label) || "決着！");
    };

    const run = async () => {
      root.hidden = false;
      document.body.classList.add("battle-short-replay-active");
      if (resultHost) {
        resultHost.hidden = true;
      }
      setCaption(replay.player_name ? `${replay.player_name} 出撃！` : "戦闘開始");
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(60, introDelay)));
      for (const event of replay.events) {
        if (finished) return;
        applyEvent(event);
        await new Promise((resolve) => window.setTimeout(resolve, Math.max(180, eventDuration)));
      }
      if (finished) return;
      resetClasses();
      setCaption(replay.result_label || "決着！");
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

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
    const buttons = Array.from(document.querySelectorAll(".js-explore-return-btn"));
    const fallback = document.getElementById("explore-return-btn");
    if (fallback && !buttons.includes(fallback)) {
      buttons.push(fallback);
    }
    if (!buttons.length) return;
    const btn = buttons[0];
    const isAdmin = String(btn.dataset.ctAdmin || "") === "1";
    if (isAdmin) return;
    const labels = Array.from(document.querySelectorAll(".js-explore-return-label"));
    const labelFallback = document.getElementById("explore-return-ct-label");
    if (labelFallback && !labels.includes(labelFallback)) {
      labels.push(labelFallback);
    }
    const readyLabel = String(btn.dataset.ctaReadyLabel || "もう一度出撃");
    const readyAtRaw = Number(btn.dataset.ctReadyAt || 0);
    const remainRaw = Number(btn.dataset.ctRemain || 0);
    const fallbackRemain = Number.isFinite(remainRaw) ? Math.max(0, Math.floor(remainRaw)) : 0;
    const readyAt = Number.isFinite(readyAtRaw) ? Math.max(0, Math.floor(readyAtRaw)) : 0;
    let timerId = null;

    const formatRemain = (totalSeconds) => {
      const remain = Math.max(0, Math.floor(Number(totalSeconds) || 0));
      const minutes = Math.floor(remain / 60);
      const seconds = remain % 60;
      return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    const render = (remain) => {
      if (remain <= 0) {
        buttons.forEach((item) => {
          item.disabled = false;
          item.textContent = String(item.dataset.ctaReadyLabel || readyLabel);
        });
        labels.forEach((item) => {
          item.textContent = "出撃可能";
        });
        return true;
      }
      const remainLabel = formatRemain(remain);
      buttons.forEach((item) => {
        item.disabled = true;
        item.textContent = `あと ${remainLabel} で出撃可能`;
      });
      labels.forEach((item) => {
        item.textContent = `次の出撃まで あと ${remainLabel}`;
      });
      return false;
    };

    const getRemain = () => {
      if (readyAt > 0) {
        return Math.max(0, readyAt - Math.floor(Date.now() / 1000));
      }
      return fallbackRemain;
    };

    const stopTicker = () => {
      if (timerId !== null) {
        window.clearInterval(timerId);
        timerId = null;
      }
    };

    const sync = () => {
      const done = render(getRemain());
      if (done) {
        stopTicker();
      }
      return done;
    };

    const startTicker = () => {
      stopTicker();
      if (sync()) return;
      timerId = window.setInterval(sync, 1000);
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
    const hpBars = {
      player: {
        root: root.querySelector('[data-replay-hp="player"]'),
        fill: root.querySelector('[data-replay-hp-fill="player"]'),
        lag: root.querySelector('[data-replay-hp-lag="player"]'),
      },
      enemy: {
        root: root.querySelector('[data-replay-hp="enemy"]'),
        fill: root.querySelector('[data-replay-hp-fill="enemy"]'),
        lag: root.querySelector('[data-replay-hp-lag="enemy"]'),
      },
    };
    const introDelay = Number(root.dataset.introDelayMs || replay.intro_delay_ms || 120);
    const eventDuration = Number(root.dataset.eventDurationMs || replay.event_duration_ms || 380);
    const outroHold = Number(root.dataset.outroHoldMs || replay.outro_hold_ms || 340);
    const hpMax = {
      player: Math.max(1, Number(replay.player_hp_max || replay.player_hp_start || 1)),
      enemy: Math.max(1, Number(replay.enemy_hp_max || replay.enemy_hp_start || 1)),
    };
    const currentHp = {
      player: Math.max(0, Number(replay.player_hp_start || hpMax.player)),
      enemy: Math.max(0, Number(replay.enemy_hp_start || hpMax.enemy)),
    };
    const lagHp = {
      player: currentHp.player,
      enemy: currentHp.enemy,
    };
    let finished = false;
    const timers = [];

    const clampRatio = (value) => {
      if (!Number.isFinite(value)) return 0;
      return Math.max(0, Math.min(1, value));
    };

    const hpRatioFor = (side, hpValue) => clampRatio(Number(hpValue || 0) / Math.max(1, hpMax[side] || 1));

    const paintHpBar = (side, hpValue, lagValue, { immediate = false } = {}) => {
      const bar = hpBars[side];
      if (!bar || !bar.fill || !bar.lag || !bar.root) return;
      const ratio = hpRatioFor(side, hpValue);
      const lagRatio = hpRatioFor(side, lagValue);
      if (immediate) {
        bar.fill.style.transition = "none";
        bar.lag.style.transition = "none";
      }
      bar.fill.style.width = `${ratio * 100}%`;
      bar.lag.style.width = `${lagRatio * 100}%`;
      bar.root.classList.toggle("is-empty", ratio <= 0.002);
      bar.root.classList.toggle("is-low", ratio > 0.002 && ratio <= 0.24);
      if (immediate) {
        void bar.root.offsetWidth;
        bar.fill.style.transition = "";
        bar.lag.style.transition = "";
      }
    };

    const initHpBars = () => {
      paintHpBar("player", currentHp.player, lagHp.player, { immediate: true });
      paintHpBar("enemy", currentHp.enemy, lagHp.enemy, { immediate: true });
    };

    const clearHpClasses = () => {
      Object.values(hpBars).forEach((bar) => {
        if (!bar || !bar.root) return;
        bar.root.classList.remove("is-hurt", "is-critical-damage", "is-bracing");
      });
    };

    const animateHpChange = (side, nextHpValue, event) => {
      const bar = hpBars[side];
      if (!bar || !bar.root) return;
      const nextHp = Math.max(0, Math.min(hpMax[side], Number(nextHpValue)));
      const previousHp = currentHp[side];
      const hpChanged = nextHp !== previousHp;
      const isCritical = Boolean(event && event.crit);
      const isBrace = String((event && event.reaction) || "") === "brace";
      const isFinish = String((event && event.reaction) || "") === "finish" || nextHp <= 0;
      if (!hpChanged && !(isBrace && nextHp > 0 && hpRatioFor(side, nextHp) <= 0.18)) {
        return;
      }

      bar.root.classList.add("is-hurt");
      if (isCritical) {
        bar.root.classList.add("is-critical-damage");
      }
      if (isBrace) {
        bar.root.classList.add("is-bracing");
      }

      const hpDropDelay = isCritical ? 170 : 130;
      const lagDelay = isCritical ? 330 : 260;

      if (hpChanged) {
        queueTimeout(() => {
          paintHpBar(side, nextHp, lagHp[side]);
          currentHp[side] = nextHp;
        }, hpDropDelay);

        queueTimeout(() => {
          lagHp[side] = nextHp;
          paintHpBar(side, currentHp[side], lagHp[side]);
        }, lagDelay);
      } else if (isBrace) {
        const actualRatio = hpRatioFor(side, nextHp);
        const braceRatio = Math.max(0.015, Math.min(actualRatio, 0.035));
        queueTimeout(() => {
          paintHpBar(side, Math.round(hpMax[side] * braceRatio), lagHp[side]);
        }, 110);
        queueTimeout(() => {
          paintHpBar(side, nextHp, lagHp[side]);
        }, 220);
      }

      if (isFinish) {
        queueTimeout(() => {
          currentHp[side] = 0;
          lagHp[side] = 0;
          paintHpBar(side, 0, 0);
        }, hpChanged ? lagDelay + 30 : 150);
      }
    };

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
      clearHpClasses();
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
      if (event && Object.prototype.hasOwnProperty.call(event, "player_hp") && event.player_hp !== null) {
        animateHpChange("player", event.player_hp, event);
      }
      if (event && Object.prototype.hasOwnProperty.call(event, "enemy_hp") && event.enemy_hp !== null) {
        animateHpChange("enemy", event.enemy_hp, event);
      }
      setCaption((event && event.label) || "決着！");
    };

    const run = async () => {
      root.hidden = false;
      document.body.classList.add("battle-short-replay-active");
      initHpBars();
      if (resultHost) {
        resultHost.hidden = true;
      }
      setCaption(replay.player_name ? `${replay.player_name} 出撃！` : "戦闘開始");
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(60, introDelay)));
      for (const event of replay.events) {
        if (finished) return;
        applyEvent(event);
        const stepDuration = Number((event && event.duration_ms) || eventDuration || 380);
        await new Promise((resolve) => window.setTimeout(resolve, Math.max(180, stepDuration)));
      }
      if (finished) return;
      resetClasses();
      setCaption("決着！");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
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

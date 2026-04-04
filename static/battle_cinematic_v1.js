(() => {
  const STORAGE_KEY = "robolabo:battle-cinematic-mode";
  const PERSISTENT_MODES = new Set(["standard", "fast"]);
  const MODE_SET = new Set(["standard", "fast", "instant"]);

  const initBattleCinematicV1 = () => {
    const root = document.getElementById("battle-short-replay");
    const dataEl = document.getElementById("battle-cinematic-v1-data");
    const followup = document.getElementById("battle-replay-followup");
    if (!root || !dataEl || !followup || !window.__uiEffectsEnabled) return;
    if ((root.dataset.cinematicVersion || "") !== "v1") return;

    let payload;
    try {
      payload = JSON.parse(dataEl.textContent || "{}");
    } catch (_error) {
      return;
    }
    if (!payload || !Array.isArray(payload.turns) || !payload.turns.length) return;

    const prefersReducedMotion = window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false;
    const stage = root.querySelector("[data-cinematic-stage]");
    const playerUnit = root.querySelector('[data-cinematic-unit="player"]');
    const enemyUnit = root.querySelector('[data-cinematic-unit="enemy"]');
    const projectile = root.querySelector("[data-cinematic-projectile]");
    const hitflash = root.querySelector("[data-cinematic-hitflash]");
    const sparks = root.querySelector("[data-cinematic-sparks]");
    const modeButtons = Array.from(root.querySelectorAll("[data-cinematic-mode]"));
    const skipButton = root.querySelector("[data-cinematic-skip]");
    const turnIndicator = root.querySelector("[data-cinematic-turn-indicator]");
    const cardTurn = root.querySelector("[data-cinematic-card-turn]");
    const cardActor = root.querySelector("[data-cinematic-card-actor]");
    const actionLabel = root.querySelector("[data-cinematic-action-label]");
    const resultLabel = root.querySelector("[data-cinematic-result-label]");
    const valueLabel = root.querySelector("[data-cinematic-value-label]");
    const statusLabel = root.querySelector("[data-cinematic-status-label]");
    const tacticalLabel = root.querySelector("[data-cinematic-tactical-label]");
    const finalBox = root.querySelector("[data-cinematic-final]");
    const hpBars = {
      player: {
        root: root.querySelector('[data-cinematic-hp="player"]'),
        fill: root.querySelector('[data-cinematic-hp-fill="player"]'),
        lag: root.querySelector('[data-cinematic-hp-lag="player"]'),
      },
      enemy: {
        root: root.querySelector('[data-cinematic-hp="enemy"]'),
        fill: root.querySelector('[data-cinematic-hp-fill="enemy"]'),
        lag: root.querySelector('[data-cinematic-hp-lag="enemy"]'),
      },
    };
    const stateBadges = {
      player: root.querySelector('[data-cinematic-state="player"]'),
      enemy: root.querySelector('[data-cinematic-state="enemy"]'),
    };

    const hpMax = {
      player: Math.max(1, Number(payload.player_hp_max || payload.player_hp_start || 1)),
      enemy: Math.max(1, Number(payload.enemy_hp_max || payload.enemy_hp_start || 1)),
    };
    const hpState = {
      player: Math.max(0, Number(payload.player_hp_start || hpMax.player)),
      enemy: Math.max(0, Number(payload.enemy_hp_start || hpMax.enemy)),
    };
    const lagHpState = {
      player: hpState.player,
      enemy: hpState.enemy,
    };

    let activeRunId = 0;
    let finished = false;
    let currentMode = PERSISTENT_MODES.has(window.localStorage?.getItem(STORAGE_KEY) || "")
      ? window.localStorage.getItem(STORAGE_KEY)
      : "standard";
    const timers = [];

    const clearTimers = () => {
      while (timers.length) {
        window.clearTimeout(timers.pop());
      }
    };

    const queueTimeout = (callback, delayMs, runId = activeRunId) => {
      const timerId = window.setTimeout(() => {
        const index = timers.indexOf(timerId);
        if (index >= 0) timers.splice(index, 1);
        if (runId !== activeRunId || finished) return;
        callback();
      }, delayMs);
      timers.push(timerId);
      return timerId;
    };

    const delay = (delayMs, runId) =>
      new Promise((resolve) => {
        queueTimeout(resolve, delayMs, runId);
      });

    const clampRatio = (value) => Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));

    const hpRatio = (side, value) => clampRatio(Number(value || 0) / Math.max(1, hpMax[side] || 1));

    const paintHp = (side, hpValue, lagValue, { immediate = false } = {}) => {
      const bar = hpBars[side];
      if (!bar || !bar.root || !bar.fill || !bar.lag) return;
      const ratio = hpRatio(side, hpValue);
      const lagRatio = hpRatio(side, lagValue);
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
      hpState.player = Math.max(0, Number(payload.player_hp_start || hpMax.player));
      hpState.enemy = Math.max(0, Number(payload.enemy_hp_start || hpMax.enemy));
      lagHpState.player = hpState.player;
      lagHpState.enemy = hpState.enemy;
      paintHp("player", hpState.player, lagHpState.player, { immediate: true });
      paintHp("enemy", hpState.enemy, lagHpState.enemy, { immediate: true });
    };

    const resetStateBadges = () => {
      Object.values(stateBadges).forEach((node) => {
        if (!node) return;
        node.textContent = "";
        node.className = "battle-cinematic-v1-state-badge";
      });
    };

    const applyStateBadge = (side, effectKey, label) => {
      const node = stateBadges[side];
      if (!node) return;
      if (!effectKey || !label) {
        node.textContent = "";
        node.className = "battle-cinematic-v1-state-badge";
        return;
      }
      node.textContent = label;
      node.className = `battle-cinematic-v1-state-badge is-active effect-${effectKey}`;
    };

    const resetTransientClasses = () => {
      clearTimers();
      root.classList.remove("is-critical", "is-finisher", "is-hit-stop");
      if (stage) {
        stage.dataset.currentActor = "";
        stage.dataset.currentTarget = "";
        stage.dataset.currentHitType = "";
      }
      [playerUnit, enemyUnit].forEach((node) => {
        if (!node) return;
        node.classList.remove("is-acting", "is-hit", "is-crit-hit", "is-evading", "is-blocking", "is-finished");
      });
      [projectile, hitflash, sparks].forEach((node) => {
        if (!node) return;
        node.className = node.className
          .split(" ")
          .filter((className) => !/^is-/.test(className) && !/^from-/.test(className) && !/^to-/.test(className) && !/^target-/.test(className))
          .join(" ");
      });
      Object.values(hpBars).forEach((bar) => {
        if (!bar || !bar.root) return;
        bar.root.classList.remove("is-hurt", "is-critical-damage", "is-bracing");
      });
    };

    const revealFollowup = () => {
      if (finished) return;
      finished = true;
      activeRunId += 1;
      clearTimers();
      resetTransientClasses();
      root.hidden = true;
      document.body.classList.remove("battle-short-replay-active");
    };

    const setMode = (nextMode, { persist = true, rerun = true } = {}) => {
      if (!MODE_SET.has(nextMode)) return;
      currentMode = nextMode;
      root.dataset.mode = currentMode;
      modeButtons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.cinematicMode === currentMode);
      });
      if (persist && PERSISTENT_MODES.has(nextMode) && window.localStorage) {
        window.localStorage.setItem(STORAGE_KEY, nextMode);
      }
      if (persist && !PERSISTENT_MODES.has(nextMode) && window.localStorage) {
        window.localStorage.removeItem(STORAGE_KEY);
      }
      if (nextMode === "instant") {
        revealFollowup();
        return;
      }
      if (rerun) {
        start();
      }
    };

    const setCardText = ({ turnText, actorText, actionText, resultText, valueText, statusText, tacticalText }) => {
      if (cardTurn && turnText !== undefined) cardTurn.textContent = turnText;
      if (cardActor && actorText !== undefined) cardActor.textContent = actorText;
      if (actionLabel && actionText !== undefined) actionLabel.textContent = actionText;
      if (resultLabel && resultText !== undefined) resultLabel.textContent = resultText;
      if (valueLabel && valueText !== undefined) valueLabel.textContent = valueText || "";
      if (statusLabel && statusText !== undefined) statusLabel.textContent = statusText || "";
      if (tacticalLabel && tacticalText !== undefined) tacticalLabel.textContent = tacticalText || "";
    };

    const applyHpAnimation = (side, nextHp, step, runId) => {
      const bar = hpBars[side];
      if (!bar || !bar.root) return;
      const hpValue = Math.max(0, Math.min(hpMax[side], Number(nextHp)));
      const previousHp = hpState[side];
      const hasDrop = hpValue !== previousHp;
      const isCrit = String(step.hit_type || "") === "crit";
      const isBrace = side === "player" && hpValue > 0 && hpRatio(side, hpValue) <= 0.12 && hasDrop;
      if (!hasDrop) return;

      bar.root.classList.add("is-hurt");
      if (isCrit) bar.root.classList.add("is-critical-damage");
      if (isBrace) bar.root.classList.add("is-bracing");

      const dropDelay = isCrit ? 170 : 120;
      const lagDelay = isCrit ? 350 : 260;
      queueTimeout(() => {
        hpState[side] = hpValue;
        paintHp(side, hpState[side], lagHpState[side]);
      }, dropDelay, runId);
      queueTimeout(() => {
        lagHpState[side] = hpValue;
        paintHp(side, hpState[side], lagHpState[side]);
      }, lagDelay, runId);
    };

    const applyStepVisuals = (step, runId) => {
      resetTransientClasses();
      if (stage) {
        stage.dataset.currentActor = step.actor || "";
        stage.dataset.currentTarget = step.target || "";
        stage.dataset.currentHitType = step.hit_type || "";
      }
      const actorUnit = step.actor === "player" ? playerUnit : enemyUnit;
      const targetUnit = step.target === "player" ? playerUnit : enemyUnit;
      actorUnit && actorUnit.classList.add("is-acting");
      if (projectile && step.projectile === "shot") {
        projectile.classList.add("is-live", `from-${step.actor}`, `to-${step.target}`);
      }
      if (step.hit_type === "miss") {
        targetUnit && targetUnit.classList.add("is-evading");
      } else if (step.hit_type === "block") {
        targetUnit && targetUnit.classList.add("is-blocking");
      } else {
        targetUnit && targetUnit.classList.add("is-hit");
        if (step.hit_type === "crit") {
          root.classList.add("is-critical", "is-hit-stop");
          targetUnit && targetUnit.classList.add("is-crit-hit");
          queueTimeout(() => {
            root.classList.remove("is-hit-stop");
          }, 140, runId);
        }
        if (hitflash) {
          hitflash.classList.add("is-live", `target-${step.target}`);
          if (step.hit_type === "crit") hitflash.classList.add("is-critical");
        }
        if (sparks && (step.hit_type === "crit" || step.is_finisher)) {
          sparks.classList.add("is-live", `target-${step.target}`);
          if (step.hit_type === "crit") sparks.classList.add("is-critical");
        }
      }
      if (step.is_finisher) {
        root.classList.add("is-finisher");
        targetUnit && targetUnit.classList.add("is-finished");
      }
      applyHpAnimation("player", step.player_hp_after, step, runId);
      applyHpAnimation("enemy", step.enemy_hp_after, step, runId);
    };

    const effectiveDelay = (delayMs) => {
      const factor = prefersReducedMotion ? 0.72 : 1;
      return Math.max(120, Math.round(Number(delayMs || 0) * factor));
    };

    const runTurn = async (turn, index, runId) => {
      const turnTotal = effectiveDelay(
        currentMode === "fast" ? turn.fast_duration_ms || 980 : turn.standard_duration_ms || 1800
      );
      const steps = Array.isArray(turn.steps) ? turn.steps : [];
      const openDelay = effectiveDelay(currentMode === "fast" ? 130 : 220);
      const summaryHold = effectiveDelay(currentMode === "fast" ? 210 : 420);
      const stepBudget = Math.max(360, turnTotal - openDelay - summaryHold);
      const stepDelay = Math.max(
        effectiveDelay(currentMode === "fast" ? 280 : 430),
        Math.round(stepBudget / Math.max(1, steps.length || 1))
      );

      if (turnIndicator) {
        turnIndicator.textContent = `TURN ${index + 1} / ${payload.turn_count || payload.turns.length}`;
      }
      setCardText({
        turnText: `TURN ${index + 1}`,
        actorText: turn.opening_label || "交戦開始",
        actionText: payload.is_boss && index === 0 ? "BOSS WARNING" : "次の動きを読む",
        resultText: payload.is_boss && index === 0 ? "圧力が高まっている" : "戦況を整理中",
        valueText: "",
        statusText: "",
        tacticalText: turn.tactical_label || "動き出す瞬間を見ている",
      });
      resetStateBadges();
      await delay(openDelay, runId);
      if (runId !== activeRunId || finished) return;

      for (const step of steps) {
        setCardText({
          actorText: `${step.actor_name} が動く`,
          actionText: step.action_label,
          resultText: step.result_label,
          valueText: step.value_label,
          statusText: "",
          tacticalText: step.tactical_label || turn.tactical_label,
        });
        applyStepVisuals(step, runId);
        await delay(stepDelay, runId);
        if (runId !== activeRunId || finished) return;
      }

      const stateLabelText = turn.status_label
        ? `${turn.status_label}${turn.status_target === "player" ? " / 味方側" : " / 敵側"}`
        : "";
      if (turn.status_target && turn.status_effect && turn.status_label) {
        applyStateBadge(turn.status_target, turn.status_effect, turn.status_label);
      }
      setCardText({
        actorText: turn.status_label ? "機構状態" : "戦況整理",
        actionText: turn.steps[turn.steps.length - 1]?.action_label || "戦況整理",
        resultText: turn.steps[turn.steps.length - 1]?.result_label || "戦況を更新",
        valueText: turn.steps[turn.steps.length - 1]?.value_label || "",
        statusText: stateLabelText,
        tacticalText: turn.tactical_label || payload.summary_label,
      });
      await delay(summaryHold, runId);
    };

    const run = async (runId) => {
      if (currentMode === "instant") {
        revealFollowup();
        return;
      }
      finished = false;
      root.hidden = false;
      document.body.classList.add("battle-short-replay-active");
      if (finalBox) finalBox.hidden = true;
      initHpBars();
      resetStateBadges();
      setCardText({
        turnText: "TURN 1",
        actorText: payload.is_boss ? "BOSS BATTLE" : "戦闘開始",
        actionText: payload.is_boss ? "警戒態勢" : "交戦開始",
        resultText: payload.player_name ? `${payload.player_name} 出撃` : "出撃",
        valueText: "",
        statusText: "",
        tacticalText: payload.is_boss ? "ボスの圧力を見極める" : "先手を見極めている",
      });

      const introDelay = effectiveDelay(
        currentMode === "fast" ? payload.fast_intro_delay_ms || 220 : payload.intro_delay_ms || 520
      );
      await delay(introDelay, runId);
      if (runId !== activeRunId || finished) return;

      for (let index = 0; index < payload.turns.length; index += 1) {
        await runTurn(payload.turns[index], index, runId);
        if (runId !== activeRunId || finished) return;
      }

      resetTransientClasses();
      if (finalBox) {
        finalBox.hidden = false;
        const finalHeading = finalBox.querySelector(".battle-cinematic-v1-final-heading");
        const finalLabel = finalBox.querySelector(".battle-cinematic-v1-final-label");
        const finalResult = finalBox.querySelector(".battle-cinematic-v1-final-result");
        if (finalHeading) finalHeading.textContent = payload.summary_heading || "今回の勝ち筋";
        if (finalLabel) finalLabel.textContent = payload.summary_label || "";
        if (finalResult) finalResult.textContent = payload.result_label || "WIN";
      }
      setCardText({
        actorText: payload.summary_heading || "今回の勝ち筋",
        actionText: payload.summary_label || "",
        resultText: payload.result_sub_label || "",
        valueText: "",
        statusText: "",
        tacticalText: payload.player_won ? "戦利品へ進みます" : "結果を整理します",
      });

      const outroHold = effectiveDelay(
        currentMode === "fast" ? payload.fast_outro_hold_ms || 380 : payload.outro_hold_ms || 860
      );
      await delay(outroHold, runId);
      if (runId !== activeRunId || finished) return;
      revealFollowup();
    };

    const start = () => {
      finished = false;
      activeRunId += 1;
      clearTimers();
      resetTransientClasses();
      run(activeRunId).catch(() => {
        revealFollowup();
      });
    };

    modeButtons.forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        setMode(button.dataset.cinematicMode || "standard", {
          persist: button.dataset.cinematicMode !== "instant",
          rerun: true,
        });
      });
    });

    skipButton &&
      skipButton.addEventListener("click", (event) => {
        event.preventDefault();
        revealFollowup();
      });

    setMode(currentMode, { persist: false, rerun: false });
    start();
  };

  document.addEventListener("DOMContentLoaded", initBattleCinematicV1);
})();

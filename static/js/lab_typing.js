(function () {
  const configEl = document.getElementById("lab-typing-config");
  const root = document.querySelector("[data-lab-typing-root]");
  if (!configEl || !root) return;

  const config = JSON.parse(configEl.textContent || "{}");
  const commands = config.commands || {};
  const enemies = config.enemies || [];
  const durationMs = Number(config.durationMs || 30000);
  const resultUrl = String(config.resultUrl || "");

  const $ = (selector) => root.querySelector(selector);
  const els = {
    time: $("[data-typing-time]"),
    score: $("[data-typing-score]"),
    combo: $("[data-typing-combo]"),
    input: $("[data-typing-input]"),
    command: $("[data-typing-command]"),
    start: $("[data-typing-start]"),
    enemyCard: $("[data-typing-enemy-card]"),
    enemyName: $("[data-typing-enemy-name]"),
    enemyKind: $("[data-typing-enemy-kind]"),
    enemyHp: $("[data-typing-enemy-hp]"),
    hpFill: $("[data-typing-hp-fill]"),
    defeated: $("[data-typing-defeated]"),
    miss: $("[data-typing-miss]"),
    warning: $("[data-typing-warning]"),
    shotLayer: $("[data-typing-shot-layer]"),
    result: $("[data-typing-result]"),
    resultBody: $("[data-typing-result-body]"),
  };

  const state = {
    started: false,
    finished: false,
    startTime: null,
    timerId: null,
    score: 0,
    combo: 0,
    maxCombo: 0,
    typedCount: 0,
    missCount: 0,
    currentCommand: "",
    currentEnemyIndex: 0,
    currentEnemyHp: enemies[0] ? Number(enemies[0].hp) : 100,
    defeatedCount: 0,
    bossReached: false,
    bossDefeated: false,
  };

  function currentEnemy() {
    return enemies[state.currentEnemyIndex] || enemies[0] || { name: "-", hp: 100, score_multiplier: 1, kind: "normal" };
  }

  function comboDamageMultiplier(combo) {
    if (combo < 10) return 1.0;
    if (combo < 20) return 1.2;
    if (combo < 30) return 1.5;
    return 2.0;
  }

  function calculateDamage(commandLength, combo) {
    return Math.floor(commandLength * 10 * comboDamageMultiplier(combo));
  }

  function calculateScore(commandLength, combo, enemyMultiplier) {
    const baseScore = commandLength * 10;
    const comboMultiplier = Math.min(Math.pow(1.05, combo), 10.0);
    return Math.floor(baseScore * comboMultiplier * Number(enemyMultiplier || 1));
  }

  function remainingMs() {
    if (!state.started || !state.startTime) return durationMs;
    return Math.max(0, durationMs - (Date.now() - state.startTime));
  }

  function pickFrom(list) {
    return list[Math.floor(Math.random() * list.length)];
  }

  function weightedPick(weightRows) {
    const total = weightRows.reduce((sum, row) => sum + row[1], 0);
    let roll = Math.random() * total;
    for (const [key, weight] of weightRows) {
      roll -= weight;
      if (roll <= 0) return key;
    }
    return weightRows[0][0];
  }

  function pickNextCommand() {
    const enemy = currentEnemy();
    let bucket;
    if (enemy.kind === "boss") {
      bucket = weightedPick([["normal", 50], ["hard", 50]]);
    } else {
      const remain = remainingMs();
      if (remain > 20000) bucket = weightedPick([["easy", 80], ["normal", 20]]);
      else if (remain > 10000) bucket = weightedPick([["easy", 30], ["normal", 60], ["hard", 10]]);
      else bucket = weightedPick([["easy", 10], ["normal", 50], ["hard", 40]]);
    }
    return pickFrom(commands[bucket] || commands.easy || ["FIRE"]);
  }

  function formatNumber(value) {
    return Number(value || 0).toLocaleString("ja-JP");
  }

  function render() {
    const enemy = currentEnemy();
    const maxHp = Number(enemy.hp || 1);
    const hp = Math.max(0, Math.ceil(state.currentEnemyHp));
    els.time.textContent = (remainingMs() / 1000).toFixed(1);
    els.score.textContent = formatNumber(state.score);
    els.combo.textContent = String(state.combo);
    els.command.textContent = state.currentCommand || "-";
    els.enemyName.textContent = enemy.name || "-";
    els.enemyKind.textContent = enemy.kind === "boss" ? "ボス" : "通常敵";
    els.enemyHp.textContent = `${hp} / ${maxHp}`;
    els.hpFill.style.width = `${Math.max(0, Math.min(100, (hp / maxHp) * 100))}%`;
    els.defeated.textContent = String(state.defeatedCount);
    els.miss.textContent = String(state.missCount);
    root.classList.toggle("is-boss", enemy.kind === "boss");
  }

  function playShotAnimation() {
    const shot = document.createElement("span");
    shot.className = "typing-shot";
    els.shotLayer.appendChild(shot);
    setTimeout(() => shot.remove(), 260);
    els.enemyCard.classList.remove("enemy-hit");
    void els.enemyCard.offsetWidth;
    els.enemyCard.classList.add("enemy-hit");
  }

  function showBossWarning() {
    els.warning.hidden = false;
    setTimeout(() => {
      els.warning.hidden = true;
    }, 1200);
  }

  function advanceEnemy() {
    state.defeatedCount += 1;
    if (state.currentEnemyIndex >= enemies.length - 1) {
      state.bossDefeated = true;
      finishGame(true);
      return;
    }
    state.currentEnemyIndex += 1;
    state.currentEnemyHp = Number(currentEnemy().hp || 100);
    if (currentEnemy().kind === "boss") {
      state.bossReached = true;
      showBossWarning();
    }
  }

  function handleSuccess() {
    const commandLength = state.currentCommand.length;
    state.combo += 1;
    state.maxCombo = Math.max(state.maxCombo, state.combo);
    state.typedCount += 1;

    const enemy = currentEnemy();
    state.score += calculateScore(commandLength, state.combo, enemy.score_multiplier);
    state.currentEnemyHp -= calculateDamage(commandLength, state.combo);

    playShotAnimation();
    if (state.currentEnemyHp <= 0) {
      advanceEnemy();
    }
    state.currentCommand = pickNextCommand();
    els.input.value = "";
    render();
  }

  function handleMiss() {
    state.combo = 0;
    state.missCount += 1;
    els.input.value = "";
    root.classList.remove("is-miss");
    void root.offsetWidth;
    root.classList.add("is-miss");
    render();
  }

  function buildPayload() {
    const enemy = currentEnemy();
    return {
      score: state.score,
      max_combo: state.maxCombo,
      typed_count: state.typedCount,
      miss_count: state.missCount,
      defeated_count: state.defeatedCount,
      boss_reached: state.bossReached,
      boss_defeated: state.bossDefeated,
      remaining_boss_hp: state.bossReached ? Math.max(0, Math.ceil(state.currentEnemyHp)) : null,
      duration_ms: Math.max(25000, Math.min(35000, Date.now() - state.startTime)),
      client_payload: {
        version: 1,
        enemy_key: enemy.key || null,
      },
    };
  }

  function resultHtml(payload, saved) {
    const bossReached = payload.boss_reached ? "達成" : "未達成";
    const bossDefeated = payload.boss_defeated ? "達成" : "未達成";
    const bossHp = payload.boss_reached ? payload.remaining_boss_hp : "-";
    const badges = [];
    if (saved && saved.is_today_best) badges.push("本日ベスト");
    if (saved && saved.is_personal_best) badges.push("自己ベスト");
    return `
      <p>${badges.map((x) => `<span class="weekly-fit-badge">${x}</span>`).join(" ")}</p>
      <ul class="lab-typing-result-list">
        <li><span>スコア</span><b>${formatNumber(payload.score)}</b></li>
        <li><span>最大コンボ</span><b>${payload.max_combo}</b></li>
        <li><span>入力成功</span><b>${payload.typed_count}</b></li>
        <li><span>ミス</span><b>${payload.miss_count}</b></li>
        <li><span>撃破数</span><b>${payload.defeated_count}体</b></li>
        <li><span>ボス到達</span><b>${bossReached}</b></li>
        <li><span>ボス撃破</span><b>${bossDefeated}</b></li>
        <li><span>ボス残HP</span><b>${bossHp}</b></li>
      </ul>`;
  }

  async function saveResult(payload) {
    if (!resultUrl) return null;
    const response = await fetch(resultUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) return null;
    return response.json();
  }

  function finishGame(byBossDefeat) {
    if (state.finished) return;
    state.finished = true;
    clearInterval(state.timerId);
    if (byBossDefeat) state.bossDefeated = true;
    els.input.disabled = true;
    els.start.disabled = false;
    const payload = buildPayload();
    saveResult(payload).then((saved) => {
      els.resultBody.innerHTML = resultHtml(payload, saved);
      els.result.hidden = false;
      els.result.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    render();
  }

  function tick() {
    if (remainingMs() <= 0) {
      finishGame(false);
      return;
    }
    render();
  }

  function startGame() {
    Object.assign(state, {
      started: true,
      finished: false,
      startTime: Date.now(),
      score: 0,
      combo: 0,
      maxCombo: 0,
      typedCount: 0,
      missCount: 0,
      currentEnemyIndex: 0,
      currentEnemyHp: enemies[0] ? Number(enemies[0].hp) : 100,
      defeatedCount: 0,
      bossReached: false,
      bossDefeated: false,
    });
    state.currentCommand = pickNextCommand();
    els.result.hidden = true;
    els.input.disabled = false;
    els.input.value = "";
    els.input.placeholder = "コマンドを入力";
    els.start.disabled = true;
    els.input.focus();
    clearInterval(state.timerId);
    state.timerId = setInterval(tick, 100);
    render();
  }

  els.input.addEventListener("input", () => {
    if (!state.started || state.finished) return;
    const typed = String(els.input.value || "").trim().toUpperCase();
    const command = String(state.currentCommand || "").toUpperCase();
    if (!typed) return;
    if (typed === command) {
      handleSuccess();
      return;
    }
    if (!command.startsWith(typed)) {
      handleMiss();
    }
  });

  els.start.addEventListener("click", startGame);
  state.currentCommand = "FIRE";
  render();
})();

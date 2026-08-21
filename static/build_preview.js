(() => {
  if (window.__buildPreviewBound) return;
  window.__buildPreviewBound = true;
  const formEl = document.getElementById("build-form");
  if (!formEl) return;
  const pickerSections = Array.from(document.querySelectorAll("details.picker-section[data-picker-section]"));
  const pickerStorageKey = "build_open_picker_section";
  const SLOT_NAMES = ["head_key", "r_arm_key", "l_arm_key", "legs_key", "decor_asset_id"];
  const STAT_LABELS = {
    hp: "耐久",
    atk: "攻撃",
    def: "防御",
    spd: "素早さ",
    acc: "命中",
    cri: "会心",
  };
  const INACTIVE_SET_BONUS_DETAIL =
    "無=耐久 / 炎=攻撃 / 水=素早さ / 雷=会心 / 風=命中 / 氷・鋼=防御 / 機械=命中 / 鉱石=会心";
  const comparePulseTargets = [
    document.querySelector(".build-preview-primary"),
    document.querySelector(".build-estimate"),
  ].filter(Boolean);

  const targetMap = {
    head: document.getElementById("pv-head"),
    rarm: document.getElementById("pv-rarm"),
    larm: document.getElementById("pv-larm"),
    legs: document.getElementById("pv-legs"),
    decor: document.getElementById("pv-decor"),
  };
  const previewTargetToInputName = {
    head: "head_key",
    rarm: "r_arm_key",
    larm: "l_arm_key",
    legs: "legs_key",
    decor: "decor_asset_id",
  };
  const previewTargetToOffsetSlot = {
    head: "head",
    rarm: "r_arm",
    larm: "l_arm",
    legs: "legs",
    decor: null,
  };
  const partImageMap = {};
  const partOffsetMap = {};
  const offsetInputMap = {};
  const scaleInputMap = {};
  const rotateInputMap = {};
  const flipInputMap = {};
  const offsetInputs = Array.from(document.querySelectorAll("input[type='range'][data-offset-slot][data-offset-axis]"));
  const scaleInputs = Array.from(document.querySelectorAll("input[type='range'][data-offset-slot][data-scale-control]"));
  const rotateInputs = Array.from(document.querySelectorAll("input[type='range'][data-offset-slot][data-rotate-control]"));
  const flipInputs = Array.from(document.querySelectorAll("input[type='checkbox'][data-offset-slot][data-flip-control]"));
  offsetInputs.forEach((input) => {
    const slot = String(input.dataset.offsetSlot || "").trim();
    const axis = String(input.dataset.offsetAxis || "").trim();
    if (!slot || !axis) return;
    offsetInputMap[slot] = offsetInputMap[slot] || {};
    offsetInputMap[slot][axis] = input;
  });
  scaleInputs.forEach((input) => {
    const slot = String(input.dataset.offsetSlot || "").trim();
    if (!slot) return;
    scaleInputMap[slot] = input;
  });
  rotateInputs.forEach((input) => {
    const slot = String(input.dataset.offsetSlot || "").trim();
    if (!slot) return;
    rotateInputMap[slot] = input;
  });
  flipInputs.forEach((input) => {
    const slot = String(input.dataset.offsetSlot || "").trim();
    if (!slot) return;
    flipInputMap[slot] = input;
  });
  document
    .querySelectorAll("input[type='radio'][data-part-key][data-img]")
    .forEach((input) => {
      const partKey = String(input.dataset.partKey || "").trim();
      if (!partKey) return;
      partImageMap[partKey] = String(input.dataset.img || "");
      partOffsetMap[partKey] = {
        x: Number(input.dataset.offsetX || 0),
        y: Number(input.dataset.offsetY || 0),
      };
    });
  window.PART_IMAGE_MAP = partImageMap;
  window.PART_OFFSET_MAP = partOffsetMap;

  function currentUserOffset(target) {
    const slot = previewTargetToOffsetSlot[target];
    if (!slot) return { x: 0, y: 0 };
    const slotInputs = offsetInputMap[slot] || {};
    const x = Number((slotInputs.x || {}).value || 0);
    const y = Number((slotInputs.y || {}).value || 0);
    return {
      x: Number.isFinite(x) ? x : 0,
      y: Number.isFinite(y) ? y : 0,
    };
  }

  function currentUserScale(target) {
    const slot = previewTargetToOffsetSlot[target];
    if (!slot) return 100;
    const input = scaleInputMap[slot];
    const value = Number((input || {}).value || 100);
    return Number.isFinite(value) ? value : 100;
  }

  function currentUserRotate(target) {
    const slot = previewTargetToOffsetSlot[target];
    if (!slot) return 0;
    const input = rotateInputMap[slot];
    const value = Number((input || {}).value || 0);
    return Number.isFinite(value) ? value : 0;
  }

  function currentUserFlip(target) {
    const slot = previewTargetToOffsetSlot[target];
    if (!slot) return 1;
    const input = flipInputMap[slot];
    return input && input.checked ? -1 : 1;
  }

  function applyPreview(target, imgUrl, offsetX, offsetY) {
    const el = targetMap[target];
    if (!el) return;
    if (!imgUrl) {
      el.setAttribute("src", "");
      el.classList.add("is-hidden");
      el.style.setProperty("--layer-offset-x", "0");
      el.style.setProperty("--layer-offset-y", "0");
      el.style.setProperty("--layer-scale", "1");
      el.style.setProperty("--layer-rotate", "0deg");
      el.style.setProperty("--layer-flip-x", "1");
      return;
    }
    const stamp = String(Date.now());
    const sep = imgUrl.includes("?") ? "&" : "?";
    el.src = `${imgUrl}${sep}v=${stamp}`;
    el.classList.remove("is-hidden");
    const baseX = Number(offsetX);
    const baseY = Number(offsetY);
    const userOffset = currentUserOffset(target);
    const dx = (Number.isFinite(baseX) ? baseX : 0) + userOffset.x;
    const dy = (Number.isFinite(baseY) ? baseY : 0) + userOffset.y;
    el.style.setProperty("--layer-offset-x", String(dx));
    el.style.setProperty("--layer-offset-y", String(dy));
    el.style.setProperty("--layer-scale", String(currentUserScale(target) / 100));
    el.style.setProperty("--layer-rotate", `${currentUserRotate(target)}deg`);
    el.style.setProperty("--layer-flip-x", String(currentUserFlip(target)));
  }

  function selectedInput(name) {
    return formEl.querySelector(`input[name='${name}']:checked`);
  }

  function syncSelectedCards() {
    formEl.querySelectorAll(".part-picker-card").forEach((card) => {
      const checked = !!card.querySelector(".picker-radio:checked");
      card.classList.toggle("is-selected", checked);
    });
  }

  function pulseComparePanels() {
    comparePulseTargets.forEach((el) => {
      el.classList.remove("is-compare-pulse");
      void el.offsetWidth;
      el.classList.add("is-compare-pulse");
    });
  }

  function statOf(input, key) {
    if (!input) return 0;
    const v = Number(input.dataset[`stat${key}`]);
    return Number.isFinite(v) ? v : 0;
  }

  function updateEstimate() {
    const slots = [
      selectedInput("head_key"),
      selectedInput("r_arm_key"),
      selectedInput("l_arm_key"),
      selectedInput("legs_key"),
    ];
    if (slots.some((s) => !s)) return;

    const total = {
      hp: 0,
      atk: 0,
      def: 0,
      spd: 0,
      acc: 0,
      cri: 0,
    };

    for (const slot of slots) {
      total.hp += statOf(slot, "Hp");
      total.atk += statOf(slot, "Atk");
      total.def += statOf(slot, "Def");
      total.spd += statOf(slot, "Spd");
      total.acc += statOf(slot, "Acc");
      total.cri += statOf(slot, "Cri");
    }

    let bonusStatus = "未発動";
    let bonusCondition = "同属性パーツ 4部位で発動";
    let bonusEffect = "属性ごとに上がる能力が変わります";
    let bonusDetail = INACTIVE_SET_BONUS_DETAIL;
    const configEl = document.getElementById("build-set-bonus-table");
    const setBonusTable = configEl ? JSON.parse(configEl.value || "{}") : {};
    const elementLabelEl = document.getElementById("build-element-label-map");
    const elementLabelMap = elementLabelEl ? JSON.parse(elementLabelEl.value || "{}") : {};
    const displayScaleEl = document.getElementById("build-display-stat-scale");
    const displayStatScale = Math.max(1, Number((displayScaleEl || {}).value || 100));
    const elements = slots.map((s) => (s.dataset.element || "").toUpperCase());
    const frameTypes = new Set(slots.map((s) => String(s.dataset.frameType || "normal").trim()).filter(Boolean));
    const isMixedFrame = frameTypes.size > 1;
    if (isMixedFrame) {
      bonusStatus = "なし";
      bonusCondition = "自由編成の混成ロボはセットボーナスなし";
      bonusEffect = "セットボーナスなし";
      bonusDetail = "実験機：自由編成のためセットボーナスなし";
    } else if (elements.every((e) => e && e === elements[0])) {
      const bonus = setBonusTable[elements[0]];
      if (Array.isArray(bonus) && bonus.length >= 2) {
        const stat = String(bonus[0] || "").toLowerCase();
        const rate = Number(bonus[1]) || 0;
        if (Object.prototype.hasOwnProperty.call(total, stat) && rate > 0) {
          const before = total[stat];
          const boosted = Math.max(before + 1, Math.ceil(before * (1 + rate)));
          total[stat] = boosted;
          bonusStatus = "発動中";
          bonusEffect = `${STAT_LABELS[stat] || stat} ${formatDisplayDelta(boosted - before, displayStatScale)}`;
          bonusDetail = `${elementLabelMap[elements[0]] || elements[0]}統一で ${STAT_LABELS[stat] || stat} が ${formatDisplayStat(before, displayStatScale)} → ${formatDisplayStat(boosted, displayStatScale)}`;
        }
      }
    }

    const power =
      total.hp * 0.8 +
      total.atk * 1.4 +
      total.def * 1.1 +
      total.spd * 1.1 +
      total.acc * 0.9 +
      total.cri * 1.2;

    const bind = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = formatDisplayStat(val, displayStatScale);
    };
    bind("est-hp", total.hp);
    bind("est-atk", total.atk);
    bind("est-def", total.def);
    bind("est-spd", total.spd);
    bind("est-acc", total.acc);
    bind("est-cri", total.cri);
    bind("est-power", Math.round(power * 10) / 10);
    setText("est-bonus-status", bonusStatus);
    setText("est-bonus-condition", bonusCondition);
    setText("est-bonus-effect", bonusEffect);
    setText("est-bonus-detail", bonusDetail);
    updateComparisonRows({
      hp: total.hp,
      atk: total.atk,
      def: total.def,
      spd: total.spd,
      acc: total.acc,
      cri: total.cri,
      power: Math.round(power * 10) / 10,
    });
    updateCandidateStylePreview(total);
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value);
  }

  function computeStyle(stats) {
    const descriptions = {
      stable: "防御・命中寄り（長期戦向き）",
      burst: "攻撃・会心寄り（一撃型）",
      desperate: "低HP寄り（速攻・リスク）",
    };
    const hp = Number(stats.hp || 0);
    const atk = Number(stats.atk || 0);
    const def = Number(stats.def || 0);
    const spd = Number(stats.spd || 0);
    const acc = Number(stats.acc || 0);
    const cri = Number(stats.cri || 0);
    const total = hp + atk + def + spd + acc + cri;
    if (total <= 0) {
      return {
        key: "stable",
        label: "安定",
        description: descriptions.stable,
        reason: "ステータス不足",
        scores: { stable: 0, burst: 0, desperate: 0 },
        nextKey: "burst",
      };
    }
    const hpN = hp / total;
    const atkN = atk / total;
    const defN = def / total;
    const spdN = spd / total;
    const accN = acc / total;
    const criN = cri / total;
    const scores = {
      stable: 0.35 * defN + 0.25 * hpN + 0.2 * accN + 0.1 * spdN + 0.05 * atkN + 0.05 * (1 - criN),
      burst: 0.35 * atkN + 0.35 * criN + 0.1 * accN + 0.1 * spdN + 0.1 * (1 - defN),
      desperate: 0.3 * atkN + 0.25 * spdN + 0.15 * criN + 0.1 * accN + 0.2 * (1 - hpN),
    };
    const order = ["stable", "burst", "desperate"];
    let best = order[0];
    for (const key of order.slice(1)) {
      if (scores[key] > scores[best]) best = key;
    }
    if (best === "stable") {
      return {
        key: best,
        label: "安定",
        description: descriptions.stable,
        reason: `防御 ${Math.round(defN * 1000) / 10}% / 耐久 ${Math.round(hpN * 1000) / 10}% が高い`,
        scores: normalizeStyleScores(scores),
        nextKey: nextStyle(scores, best),
      };
    }
    if (best === "burst") {
      return {
        key: best,
        label: "爆発",
        description: descriptions.burst,
        reason: `攻撃 ${Math.round(atkN * 1000) / 10}% / 会心 ${Math.round(criN * 1000) / 10}% が高い`,
        scores: normalizeStyleScores(scores),
        nextKey: nextStyle(scores, best),
      };
    }
    return {
      key: best,
      label: "背水",
      description: descriptions.desperate,
      reason: `低耐久傾向 ${Math.round((1 - hpN) * 1000) / 10}% / 素早さ ${Math.round(spdN * 1000) / 10}% が高い`,
      scores: normalizeStyleScores(scores),
      nextKey: nextStyle(scores, best),
    };
  }

  function normalizeStyleScores(scores) {
    const keys = ["stable", "burst", "desperate"];
    const raw = {};
    let total = 0;
    keys.forEach((key) => {
      raw[key] = Math.max(0, Number(scores[key] || 0));
      total += raw[key];
    });
    if (total <= 0) return { stable: 0, burst: 0, desperate: 0 };
    const exact = {};
    const base = {};
    let used = 0;
    keys.forEach((key) => {
      exact[key] = (raw[key] / total) * 100;
      base[key] = Math.floor(exact[key]);
      used += base[key];
    });
    keys
      .slice()
      .sort((a, b) => (exact[b] - base[b]) - (exact[a] - base[a]))
      .slice(0, 100 - used)
      .forEach((key) => {
        base[key] += 1;
      });
    return base;
  }

  function nextStyle(scores, currentKey) {
    const keys = ["stable", "burst", "desperate"].filter((key) => key !== currentKey);
    return keys.sort((a, b) => Number(scores[b] || 0) - Number(scores[a] || 0))[0] || "";
  }

  function updateCandidateStylePreview(stats) {
    const box = document.getElementById("candidate-style-preview");
    if (!box) return;
    const gauge = box.querySelector(".style-gauge");
    if (!gauge) return;
    const style = computeStyle(stats);
    const labelMap = { stable: "安定", burst: "爆発", desperate: "背水" };
    const currentLabel = gauge.querySelector("[data-style-current-label]");
    if (currentLabel) currentLabel.textContent = `現在: ${style.label}`;
    const nextLabel = gauge.querySelector("[data-style-next-label]");
    if (nextLabel && style.nextKey) nextLabel.textContent = `次の傾向: ${labelMap[style.nextKey] || style.nextKey}`;
    gauge.querySelectorAll(".style-gauge-row[data-style-key]").forEach((row) => {
      const key = row.dataset.styleKey;
      const score = Number((style.scores || {})[key] || 0);
      row.classList.toggle("is-current", key === style.key);
      row.classList.toggle("is-next", key === style.nextKey && key !== style.key);
      const fill = row.querySelector(".style-gauge-fill");
      const scoreEl = row.querySelector(".style-gauge-score");
      if (fill) fill.value = Math.max(0, Math.min(100, score));
      if (scoreEl) scoreEl.textContent = String(score);
    });
  }

  function updateComparisonRows(candidate) {
    const current = {
      hp: Number((document.getElementById("build-current-hp") || {}).value || 0),
      atk: Number((document.getElementById("build-current-atk") || {}).value || 0),
      def: Number((document.getElementById("build-current-def") || {}).value || 0),
      spd: Number((document.getElementById("build-current-spd") || {}).value || 0),
      acc: Number((document.getElementById("build-current-acc") || {}).value || 0),
      cri: Number((document.getElementById("build-current-cri") || {}).value || 0),
      power: Number((document.getElementById("build-current-power") || {}).value || 0),
    };
    for (const key of ["hp", "atk", "def", "spd", "acc", "cri", "power"]) {
      const currentValue = Number(current[key] || 0);
      const candidateValue = Number(candidate[key] || 0);
      const delta = candidateValue - currentValue;
      const showCurrent = key === "power" ? Math.round(currentValue * 10) / 10 : Math.round(currentValue);
      const showCandidate = key === "power" ? Math.round(candidateValue * 10) / 10 : Math.round(candidateValue);
      const showDelta = key === "power" ? Math.round(delta * 10) / 10 : Math.round(delta);
      setText(`cmp-${key}-current`, formatDisplayStat(showCurrent));
      setText(`cmp-${key}-candidate`, formatDisplayStat(showCandidate));
      setText(`cmp-${key}-delta`, formatDisplayDelta(showDelta));
    }
  }

  function currentDisplayStatScale() {
    const displayScaleEl = document.getElementById("build-display-stat-scale");
    return Math.max(1, Number((displayScaleEl || {}).value || 100));
  }

  function formatDisplayStat(value, scale) {
    const numeric = Number(value || 0);
    const useScale = Math.max(1, Number(scale || currentDisplayStatScale()));
    if (!Number.isFinite(numeric)) return "0";
    return String(Math.round(numeric * useScale)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function formatDisplayDelta(value, scale) {
    const numeric = Number(value || 0);
    const useScale = Math.max(1, Number(scale || currentDisplayStatScale()));
    if (!Number.isFinite(numeric)) return "±0";
    const scaled = Math.round(numeric * useScale);
    if (scaled === 0) return "±0";
    const body = String(Math.abs(scaled)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return scaled > 0 ? `+${body}` : `-${body}`;
  }

  function openPickerSection(sectionName) {
    if (!sectionName) return;
    pickerSections.forEach((section) => {
      const key = section.dataset.pickerSection;
      section.open = key === sectionName;
    });
  }

  function syncOffsetOutput(slot, axis) {
    const input = (((offsetInputMap[slot] || {})[axis]) || null);
    const output = document.getElementById(`${slot}_offset_${axis}_value`);
    if (!input || !output) return;
    const val = Number(input.value || 0);
    output.textContent = String(Number.isFinite(val) ? val : 0);
  }

  function syncScaleOutput(slot) {
    const input = scaleInputMap[slot] || null;
    const output = document.getElementById(`${slot}_scale_percent_value`);
    if (!input || !output) return;
    const val = Number(input.value || 100);
    output.textContent = `${Number.isFinite(val) ? val : 100}%`;
  }

  function syncRotateOutput(slot) {
    const input = rotateInputMap[slot] || null;
    const output = document.getElementById(`${slot}_rotate_degrees_value`);
    if (!input || !output) return;
    const val = Number(input.value || 0);
    output.textContent = `${Number.isFinite(val) ? val : 0}deg`;
  }

  function syncAllOffsetOutputs() {
    Object.keys(offsetInputMap).forEach((slot) => {
      syncOffsetOutput(slot, "x");
      syncOffsetOutput(slot, "y");
    });
    Object.keys(scaleInputMap).forEach((slot) => {
      syncScaleOutput(slot);
    });
    Object.keys(rotateInputMap).forEach((slot) => {
      syncRotateOutput(slot);
    });
  }

  pickerSections.forEach((section) => {
    section.addEventListener("toggle", () => {
      if (!section.open) return;
      const key = section.dataset.pickerSection;
      if (!key) return;
      openPickerSection(key);
      try {
        localStorage.setItem(pickerStorageKey, key);
      } catch (_err) {
        // Storage can fail in private mode; ignore and keep UI functional.
      }
    });
  });

  try {
    const lastSection = localStorage.getItem(pickerStorageKey);
    if (lastSection) {
      openPickerSection(lastSection);
    }
  } catch (_err) {
    // no-op
  }

  function syncPreviewFromSelection(input) {
    if (!input || input.type !== "radio") return;
    const target = String(input.dataset.previewTarget || "").trim();
    if (!target) return;
    const partKey = String(input.dataset.partKey || "").trim();
    const mappedImg = partKey ? partImageMap[partKey] : "";
    const mappedOffset = partKey ? partOffsetMap[partKey] : null;
    applyPreview(
      target,
      mappedImg || input.dataset.img || "",
      mappedOffset ? mappedOffset.x : input.dataset.offsetX || "0",
      mappedOffset ? mappedOffset.y : input.dataset.offsetY || "0"
    );
  }

  function refreshPreviewTarget(target) {
    const inputName = previewTargetToInputName[target];
    if (!inputName) return;
    syncPreviewFromSelection(selectedInput(inputName));
  }

  function syncAllPreviews() {
    SLOT_NAMES.forEach((slotName) => {
      syncPreviewFromSelection(selectedInput(slotName));
    });
  }

  SLOT_NAMES.forEach((slotName) => {
    formEl.querySelectorAll(`input[type='radio'][name='${slotName}']`).forEach((input) => {
      input.addEventListener("change", () => {
        try {
          syncSelectedCards();
          syncPreviewFromSelection(input);
          updateEstimate();
          pulseComparePanels();
        } catch (err) {
          console.error("[build_preview] update failed", err);
        }
      });
    });
  });

  offsetInputs.forEach((input) => {
    input.addEventListener("input", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      const axis = String(input.dataset.offsetAxis || "").trim();
      syncOffsetOutput(slot, axis);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
    input.addEventListener("change", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      const axis = String(input.dataset.offsetAxis || "").trim();
      syncOffsetOutput(slot, axis);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
  });

  scaleInputs.forEach((input) => {
    input.addEventListener("input", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      syncScaleOutput(slot);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
    input.addEventListener("change", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      syncScaleOutput(slot);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
  });

  rotateInputs.forEach((input) => {
    input.addEventListener("input", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      syncRotateOutput(slot);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
    input.addEventListener("change", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      syncRotateOutput(slot);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
  });

  flipInputs.forEach((input) => {
    input.addEventListener("change", () => {
      const slot = String(input.dataset.offsetSlot || "").trim();
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
  });

  formEl.querySelectorAll("button[data-offset-reset]").forEach((button) => {
    button.addEventListener("click", () => {
      const slot = String(button.dataset.offsetReset || "").trim();
      if (!slot || !offsetInputMap[slot]) return;
      if (offsetInputMap[slot].x) offsetInputMap[slot].x.value = "0";
      if (offsetInputMap[slot].y) offsetInputMap[slot].y.value = "0";
      if (scaleInputMap[slot]) scaleInputMap[slot].value = "100";
      if (rotateInputMap[slot]) rotateInputMap[slot].value = "0";
      if (flipInputMap[slot]) flipInputMap[slot].checked = false;
      syncOffsetOutput(slot, "x");
      syncOffsetOutput(slot, "y");
      syncScaleOutput(slot);
      syncRotateOutput(slot);
      const target = Object.entries(previewTargetToOffsetSlot).find(([, value]) => value === slot);
      if (target) refreshPreviewTarget(target[0]);
    });
  });

  syncSelectedCards();
  syncAllOffsetOutputs();
  syncAllPreviews();

  updateEstimate();
  window.addEventListener("pageshow", () => {
    try {
      syncSelectedCards();
      syncAllOffsetOutputs();
      syncAllPreviews();
      updateEstimate();
    } catch (err) {
      console.error("[build_preview] pageshow sync failed", err);
    }
  });
})();

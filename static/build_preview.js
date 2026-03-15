(() => {
  if (window.__buildPreviewBound) return;
  window.__buildPreviewBound = true;
  const formEl = document.getElementById("build-form");
  if (!formEl) return;
  const pickerSections = Array.from(document.querySelectorAll("details.picker-section[data-picker-section]"));
  const pickerStorageKey = "build_open_picker_section";
  const SLOT_NAMES = ["head_key", "r_arm_key", "l_arm_key", "legs_key", "decor_asset_id"];

  const targetMap = {
    head: document.getElementById("pv-head"),
    rarm: document.getElementById("pv-rarm"),
    larm: document.getElementById("pv-larm"),
    legs: document.getElementById("pv-legs"),
    decor: document.getElementById("pv-decor"),
  };
  const partImageMap = {};
  const partOffsetMap = {};
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

  function applyPreview(target, imgUrl, offsetX, offsetY) {
    const el = targetMap[target];
    if (!el) return;
    if (!imgUrl) {
      el.setAttribute("src", "");
      el.classList.add("is-hidden");
      el.style.setProperty("--layer-offset-x", "0");
      el.style.setProperty("--layer-offset-y", "0");
      return;
    }
    const stamp = String(Date.now());
    const sep = imgUrl.includes("?") ? "&" : "?";
    el.src = `${imgUrl}${sep}v=${stamp}`;
    el.classList.remove("is-hidden");
    const dx = Number(offsetX);
    const dy = Number(offsetY);
    el.style.setProperty("--layer-offset-x", Number.isFinite(dx) ? String(dx) : "0");
    el.style.setProperty("--layer-offset-y", Number.isFinite(dy) ? String(dy) : "0");
  }

  function selectedInput(name) {
    return formEl.querySelector(`input[name='${name}']:checked`);
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

    let bonusText = "セットボーナス: なし";
    const configEl = document.getElementById("build-set-bonus-table");
    const setBonusTable = configEl ? JSON.parse(configEl.value || "{}") : {};
    const elements = slots.map((s) => (s.dataset.element || "").toUpperCase());
    if (elements.every((e) => e && e === elements[0])) {
      const bonus = setBonusTable[elements[0]];
      if (Array.isArray(bonus) && bonus.length >= 2) {
        const stat = String(bonus[0] || "").toLowerCase();
        const rate = Number(bonus[1]) || 0;
        if (Object.prototype.hasOwnProperty.call(total, stat) && rate > 0) {
          const boosted = Math.max(total[stat] + 1, Math.ceil(total[stat] * (1 + rate)));
          total[stat] = boosted;
          bonusText = `セットボーナス: ${elements[0]} (+${Math.round(rate * 100)}%)`;
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
      if (el) el.textContent = String(val);
    };
    bind("est-hp", total.hp);
    bind("est-atk", total.atk);
    bind("est-def", total.def);
    bind("est-spd", total.spd);
    bind("est-acc", total.acc);
    bind("est-cri", total.cri);
    bind("est-power", Math.round(power * 10) / 10);
    const bonusEl = document.getElementById("est-bonus");
    if (bonusEl) bonusEl.textContent = bonusText;
    updateComparisonRows({
      hp: total.hp,
      atk: total.atk,
      def: total.def,
      spd: total.spd,
      acc: total.acc,
      cri: total.cri,
      power: Math.round(power * 10) / 10,
    });
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
      return { key: "stable", label: "安定", description: descriptions.stable, reason: "ステータス不足" };
    }
    const hpN = hp / total;
    const atkN = atk / total;
    const defN = def / total;
    const spdN = spd / total;
    const accN = acc / total;
    const criN = cri / total;
    const scores = {
      stable: 0.35 * defN + 0.25 * hpN + 0.2 * accN + 0.1 * spdN + 0.05 * atkN + 0.05 * (1 - criN),
      desperate: 0.3 * atkN + 0.25 * spdN + 0.15 * criN + 0.1 * accN + 0.2 * (1 - hpN),
      burst: 0.35 * atkN + 0.35 * criN + 0.1 * accN + 0.1 * spdN + 0.1 * (1 - defN),
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
      };
    }
    if (best === "burst") {
      return {
        key: best,
        label: "爆発",
        description: descriptions.burst,
        reason: `攻撃 ${Math.round(atkN * 1000) / 10}% / 会心 ${Math.round(criN * 1000) / 10}% が高い`,
      };
    }
    return {
      key: best,
      label: "背水",
      description: descriptions.desperate,
      reason: `低耐久傾向 ${Math.round((1 - hpN) * 1000) / 10}% / 素早さ ${Math.round(spdN * 1000) / 10}% が高い`,
    };
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
      setText(`cmp-${key}-current`, showCurrent);
      setText(`cmp-${key}-candidate`, showCandidate);
      setText(`cmp-${key}-delta`, showDelta > 0 ? `+${showDelta}` : `${showDelta}`);
    }
  }

  function openPickerSection(sectionName) {
    if (!sectionName) return;
    pickerSections.forEach((section) => {
      const key = section.dataset.pickerSection;
      section.open = key === sectionName;
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

  function syncAllPreviews() {
    SLOT_NAMES.forEach((slotName) => {
      syncPreviewFromSelection(selectedInput(slotName));
    });
  }

  SLOT_NAMES.forEach((slotName) => {
    formEl.querySelectorAll(`input[type='radio'][name='${slotName}']`).forEach((input) => {
      input.addEventListener("change", () => {
        try {
          syncPreviewFromSelection(input);
          updateEstimate();
        } catch (err) {
          console.error("[build_preview] update failed", err);
        }
      });
    });
  });

  syncAllPreviews();

  updateEstimate();
  window.addEventListener("pageshow", () => {
    try {
      syncAllPreviews();
      updateEstimate();
    } catch (err) {
      console.error("[build_preview] pageshow sync failed", err);
    }
  });
})();

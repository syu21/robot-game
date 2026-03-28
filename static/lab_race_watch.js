(function () {
  const root = document.querySelector("[data-lab-race-root='1']");
  if (!root) return;

  const framesEl = document.getElementById("lab-race-frames-json");
  const entriesEl = document.getElementById("lab-race-entries-json");
  if (!framesEl || !entriesEl) return;

  let frames = [];
  let entryMeta = [];
  try {
    frames = JSON.parse(framesEl.textContent || "[]");
  } catch (err) {
    frames = [];
  }
  try {
    entryMeta = JSON.parse(entriesEl.textContent || "[]");
  } catch (err) {
    entryMeta = [];
  }
  if (!Array.isArray(frames) || frames.length === 0) return;

  const track = root.querySelector("[data-lab-race-track='1']");
  const pack = root.querySelector("[data-lab-race-pack='1']");
  const leaderboard = root.querySelector("[data-lab-race-leaderboard='1']");
  const eventsBox = root.querySelector("[data-lab-race-events='1']");
  const roster = root.querySelector("[data-lab-race-roster='1']");
  const frameLabel = root.querySelector("[data-lab-race-frame-label]");
  const segmentNodes = Array.prototype.slice.call(root.querySelectorAll("[data-lab-race-segment-index]"));
  if (!track || !pack || !leaderboard || !eventsBox || !roster || !frameLabel) return;

  const laneCount = Math.max(1, Number(track.dataset.laneCount || 8));
  const entryMetaByOrder = new Map(
    (Array.isArray(entryMeta) ? entryMeta : []).map(function (item) {
      return [String(item.entry_order), item];
    })
  );
  const runnerByOrder = new Map();
  const recentEvents = [];

  let current = 0;
  let lastAdvancedFrame = -1;

  const FRAME_DELAY_MS = 280;
  const MAX_EVENT_LINES = 8;

  const stateLabels = {
    run: "巡航",
    recover: "立て直し",
    boost: "加速",
    dash: "会心",
    warp: "ワープ",
    hit_bar: "激突",
    pitfall: "落下",
    slip: "スリップ",
    reverse: "逆走",
    slow: "減速",
    finish: "完走",
    clash: "接触",
  };

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function numeric(value, fallback) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function metaFor(entryOrder) {
    return entryMetaByOrder.get(String(entryOrder)) || {};
  }

  function stateLabelFor(stateKey) {
    return stateLabels[String(stateKey || "run")] || "巡航";
  }

  function iconUrlForMeta(meta) {
    return String(meta.track_icon_url || meta.icon_url || meta.scene_url || "");
  }

  function sortByRank(entries) {
    return entries.slice().sort(function (left, right) {
      const leftRank = Number(left.rank_estimate || 99);
      const rightRank = Number(right.rank_estimate || 99);
      if (leftRank !== rightRank) return leftRank - rightRank;
      return Number(left.entry_order || 0) - Number(right.entry_order || 0);
    });
  }

  function segmentIndexForEntry(entry) {
    if (typeof entry.segment_index === "number") {
      return clamp(Number(entry.segment_index), 0, 9);
    }
    return clamp(Math.floor(numeric(entry.x, 0) / 10), 0, 9);
  }

  function ensureIcon(url, alt, className) {
    if (!url) return null;
    const img = document.createElement("img");
    img.className = className;
    img.src = url;
    img.alt = alt;
    return img;
  }

  function ensureRunner(entry) {
    const key = String(entry.entry_order);
    if (runnerByOrder.has(key)) return runnerByOrder.get(key);

    const meta = metaFor(key);
    const runner = document.createElement("div");
    runner.className = "lab-race-track-runner";
    runner.dataset.entryOrder = key;

    const trails = document.createElement("span");
    trails.className = "lab-race-track-runner-trails";
    runner.appendChild(trails);

    const smoke = document.createElement("span");
    smoke.className = "lab-race-track-runner-smoke";
    runner.appendChild(smoke);

    const plate = document.createElement("span");
    plate.className = "lab-race-track-runner-plate";
    runner.appendChild(plate);

    const sprite = document.createElement("span");
    sprite.className = "lab-race-track-runner-sprite";
    const icon = ensureIcon(iconUrlForMeta(meta), String(meta.display_name || ("entry " + key)), "lab-race-track-runner-img");
    if (icon) sprite.appendChild(icon);
    runner.appendChild(sprite);

    const badge = document.createElement("span");
    badge.className = "lab-race-track-runner-no";
    badge.textContent = key;
    runner.appendChild(badge);

    const focus = document.createElement("span");
    focus.className = "lab-race-track-runner-focus";
    focus.textContent = "YOU";
    runner.appendChild(focus);

    const finish = document.createElement("span");
    finish.className = "lab-race-track-runner-finish";
    finish.textContent = "GOAL";
    runner.appendChild(finish);

    pack.appendChild(runner);
    runnerByOrder.set(key, runner);
    return runner;
  }

  function paintSegments(entries, frameEvents) {
    const byIndex = {};
    segmentNodes.forEach(function (node) {
      const idx = String(node.dataset.labRaceSegmentIndex || node.getAttribute("data-lab-race-segment-index") || "");
      if (!byIndex[idx]) byIndex[idx] = [];
      byIndex[idx].push(node);
      node.classList.remove("is-live", "is-event", "is-user-segment");
    });

    const ordered = sortByRank(entries);
    const leader = ordered[0];
    const userEntry = entries.find(function (entry) {
      return Boolean(metaFor(entry.entry_order).is_user_entry);
    });

    if (leader) {
      const leaderNodes = byIndex[String(segmentIndexForEntry(leader))] || [];
      leaderNodes.forEach(function (node) {
        node.classList.add("is-live");
      });
    }
    if (userEntry) {
      const userNodes = byIndex[String(segmentIndexForEntry(userEntry))] || [];
      userNodes.forEach(function (node) {
        node.classList.add("is-user-segment");
      });
    }

    (Array.isArray(frameEvents) ? frameEvents : []).forEach(function (event) {
      const segmentIndex =
        typeof event.segment_index === "number"
          ? event.segment_index
          : segmentIndexForEntry(
              entries.find(function (entry) {
                return Number(entry.entry_order) === Number(event.entry_order);
              }) || {}
            );
      const nodes = byIndex[String(segmentIndex)] || [];
      nodes.forEach(function (node) {
        node.classList.add("is-event");
      });
    });
  }

  function pushFrameEvents(frame) {
    if (!frame || !Array.isArray(frame.events) || frame.events.length === 0) return;
    frame.events
      .slice()
      .reverse()
      .forEach(function (event, idx) {
        const meta = metaFor(event.entry_order);
        recentEvents.unshift({
          key: String(frame.frame_no) + ":" + String(idx),
          text:
            String(meta.display_name || ("#" + String(event.entry_order))) +
            " が " +
            String(event.label || event.type || "event"),
          type: String(event.type || "run"),
          isUser: Boolean(meta.is_user_entry),
        });
      });
    recentEvents.splice(MAX_EVENT_LINES);
  }

  function renderEvents() {
    if (!recentEvents.length) {
      eventsBox.textContent = "スタート待機中...";
      return;
    }
    eventsBox.innerHTML = "";
    recentEvents.forEach(function (event) {
      const line = document.createElement("div");
      line.className = "lab-race-event-item type-" + String(event.type || "run");
      if (event.isUser) {
        line.classList.add("is-user-entry");
      }

      const badge = document.createElement("span");
      badge.className = "lab-race-event-badge";
      badge.textContent = stateLabelFor(event.type);
      line.appendChild(badge);

      const text = document.createElement("span");
      text.className = "lab-race-event-text";
      text.textContent = event.text;
      line.appendChild(text);

      eventsBox.appendChild(line);
    });
  }

  function renderLeaderboard(entries) {
    leaderboard.innerHTML = "";
    sortByRank(entries).forEach(function (entry) {
      const meta = metaFor(entry.entry_order);
      const row = document.createElement("div");
      row.className = "lab-race-live-row";
      row.classList.add("rank-" + String(entry.rank_estimate || 0));
      if (meta.is_user_entry) {
        row.classList.add("is-user-entry");
      }

      const rank = document.createElement("div");
      rank.className = "lab-race-live-rank";
      rank.textContent = String(entry.rank_estimate || "-");
      row.appendChild(rank);

      const iconWrap = document.createElement("div");
      iconWrap.className = "lab-race-live-icon";
      const icon = ensureIcon(iconUrlForMeta(meta), String(meta.display_name || "lab racer"), "lab-race-live-icon-img");
      if (icon) iconWrap.appendChild(icon);
      row.appendChild(iconWrap);

      const copy = document.createElement("div");
      copy.className = "lab-race-live-copy";

      const name = document.createElement("div");
      name.className = "lab-race-live-name";
      name.textContent = String(meta.display_name || ("#" + String(entry.entry_order)));
      copy.appendChild(name);

      const owner = document.createElement("div");
      owner.className = "lab-race-live-owner";
      owner.textContent = String(meta.owner_label || "LAB ENEMY");
      copy.appendChild(owner);

      row.appendChild(copy);

      const metaCol = document.createElement("div");
      metaCol.className = "lab-race-live-meta";

      const state = document.createElement("span");
      state.className = "lab-race-live-state state-" + String(entry.state || "run");
      state.textContent = stateLabelFor(entry.state);
      metaCol.appendChild(state);

      const progress = document.createElement("span");
      progress.className = "lab-race-live-progress";
      progress.textContent = String(Math.round(Number(entry.x || 0))) + "%";
      metaCol.appendChild(progress);

      row.appendChild(metaCol);
      leaderboard.appendChild(row);
    });
  }

  function renderRoster(entries) {
    roster.innerHTML = "";
    sortByRank(entries).forEach(function (entry) {
      const meta = metaFor(entry.entry_order);
      const card = document.createElement("div");
      card.className = "lab-race-roster-card";
      card.classList.add("rank-" + String(entry.rank_estimate || 0));
      if (meta.is_user_entry) {
        card.classList.add("is-user-entry");
      }

      const head = document.createElement("div");
      head.className = "lab-race-roster-head";

      const iconWrap = document.createElement("div");
      iconWrap.className = "lab-race-roster-icon";
      const icon = ensureIcon(iconUrlForMeta(meta), String(meta.display_name || "lab racer"), "lab-race-roster-icon-img");
      if (icon) iconWrap.appendChild(icon);
      head.appendChild(iconWrap);

      const copy = document.createElement("div");
      copy.className = "lab-race-roster-copy";

      const name = document.createElement("div");
      name.className = "lab-race-roster-name";
      name.textContent = String(meta.display_name || ("#" + String(entry.entry_order)));
      copy.appendChild(name);

      const owner = document.createElement("div");
      owner.className = "lab-race-roster-owner";
      owner.textContent = String(meta.owner_label || "LAB ENEMY");
      copy.appendChild(owner);

      head.appendChild(copy);

      const rank = document.createElement("span");
      rank.className = "lab-race-roster-rank";
      rank.textContent = String(entry.rank_estimate || "-") + "位";
      head.appendChild(rank);

      card.appendChild(head);

      const bar = document.createElement("div");
      bar.className = "lab-race-roster-progress";
      const fill = document.createElement("span");
      fill.className = "lab-race-roster-progress-fill";
      fill.style.width = String(clamp(Number(entry.x || 0), 0, 100)) + "%";
      bar.appendChild(fill);
      card.appendChild(bar);

      const foot = document.createElement("div");
      foot.className = "lab-race-roster-foot";

      const lane = document.createElement("span");
      lane.className = "lab-race-roster-lane";
      lane.textContent =
        "L" +
        String(
          clamp(
            numeric(entry.lane_index != null ? entry.lane_index : entry.lane, 0),
            0,
            99
          ) + 1
        );
      foot.appendChild(lane);

      const state = document.createElement("span");
      state.className = "lab-race-roster-state state-" + String(entry.state || "run");
      state.textContent = stateLabelFor(entry.state);
      foot.appendChild(state);

      card.appendChild(foot);
      roster.appendChild(card);
    });
  }

  function renderFrame(frameIndex, options) {
    const config = options || {};
    const frame = frames[frameIndex];
    if (!frame || !Array.isArray(frame.entries)) return;

    if (config.advanceLog !== false && frameIndex > lastAdvancedFrame) {
      for (let idx = lastAdvancedFrame + 1; idx <= frameIndex; idx += 1) {
        pushFrameEvents(frames[idx]);
      }
      lastAdvancedFrame = frameIndex;
    }

    const trackWidth = Math.max(track.clientWidth, 320);
    const trackHeight = Math.max(track.clientHeight, 220);
    const laneHeight = trackHeight / laneCount;
    const runnerSize = clamp(laneHeight - 14, 30, 36);
    const startInset = 14;
    const endInset = 46;
    const travelWidth = Math.max(160, trackWidth - startInset - endInset - runnerSize);

    frame.entries.forEach(function (entry) {
      const runner = ensureRunner(entry);
      const meta = metaFor(entry.entry_order);
      const rankValue = clamp(Number(entry.rank_estimate || 8), 1, 99);
      const stateKey = String(entry.state || "run");
      const laneIndex = clamp(
        numeric(entry.lane_index != null ? entry.lane_index : entry.lane, 0),
        0,
        laneCount - 1
      );
      const boundedX = clamp(numeric(entry.x, 0), 0, 100);
      let posX = startInset + (travelWidth * boundedX) / 100;
      let posY = laneHeight * laneIndex + (laneHeight - runnerSize) / 2;
      let scale = 1;
      let rotate = 0;
      let offsetX = 0;
      let offsetY = Math.sin(frameIndex * 0.35 + laneIndex * 0.8) * 1.4;

      if (stateKey === "boost" || stateKey === "dash") {
        scale = 1.06;
      } else if (stateKey === "warp") {
        scale = 1.12;
      } else if (stateKey === "slow") {
        scale = 0.98;
      } else if (stateKey === "hit_bar") {
        rotate = Math.sin(frameIndex * 1.4 + laneIndex) * 16;
      } else if (stateKey === "pitfall") {
        offsetY += Math.abs(Math.sin(frameIndex * 1.1 + laneIndex)) * 8 + 2;
        scale = 0.97;
      } else if (stateKey === "slip") {
        offsetX += Math.sin(frameIndex * 1.8 + laneIndex) * 8;
        rotate = Math.sin(frameIndex * 1.7 + laneIndex) * 10;
      } else if (stateKey === "reverse") {
        offsetX -= 8;
        rotate = -8;
      } else if (stateKey === "finish") {
        scale = 1.08;
      }

      runner.className = "lab-race-track-runner state-" + stateKey + " rank-" + String(rankValue);
      if (meta.is_user_entry) {
        runner.classList.add("is-user-entry");
      }

      runner.style.width = String(runnerSize) + "px";
      runner.style.height = String(runnerSize) + "px";
      runner.style.transform =
        "translate(" +
        String(Math.round(posX + offsetX)) +
        "px, " +
        String(Math.round(posY + offsetY)) +
        "px) rotate(" +
        String(rotate) +
        "deg) scale(" +
        String(scale) +
        ")";
      runner.style.zIndex = String(100 + laneCount - laneIndex);
      runner.dataset.segmentIndex = String(segmentIndexForEntry(entry));
    });

    frameLabel.textContent = String(frameIndex + 1) + " / " + String(frames.length);
    paintSegments(frame.entries, frame.events || []);
    renderLeaderboard(frame.entries);
    renderRoster(frame.entries);
    renderEvents();
  }

  renderFrame(current, { advanceLog: true });

  window.addEventListener("resize", function () {
    renderFrame(current, { advanceLog: false });
  });

  const timer = window.setInterval(function () {
    current += 1;
    if (current >= frames.length) {
      window.clearInterval(timer);
      current = frames.length - 1;
    }
    renderFrame(current, { advanceLog: true });
  }, FRAME_DELAY_MS);
})();

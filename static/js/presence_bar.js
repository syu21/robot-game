(() => {
  const root = document.querySelector("[data-presence-root]");
  if (!root) return;

  const apiUrl = root.dataset.presenceApiUrl || "";
  const modalLimit = Number(root.dataset.presenceModalLimit || "24") || 24;
  const titleNode = root.querySelector("[data-presence-title]");
  const subtitleNode = root.querySelector("[data-presence-subtitle]");
  const iconsNode = root.querySelector("[data-presence-icons]");
  const listNode = root.querySelector("[data-presence-list]");
  const modal = root.querySelector("[data-presence-modal]");
  const openBtn = root.querySelector("[data-presence-open]");
  const closeBtn = root.querySelector("[data-presence-close]");
  let timerId = null;
  let isModalOpen = false;

  const clearChildren = (node) => {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  };

  const buildUrl = (limit) => {
    const url = new URL(apiUrl, window.location.origin);
    url.searchParams.set("limit", String(limit));
    return url.toString();
  };

  const setText = (node, value) => {
    if (node) node.textContent = String(value || "");
  };

  const renderIcons = (entries, count) => {
    if (!iconsNode) return;
    clearChildren(iconsNode);
    entries.slice(0, 8).forEach((entry) => {
      const wrap = document.createElement("span");
      wrap.className = `presence-avatar is-${entry.tone || "idle"}`;
      wrap.title = `${entry.display_name || "研究員"} / ${entry.state_label || "探索待機中"}`;
      const img = document.createElement("img");
      img.src = entry.robot_icon_32_url || "";
      img.alt = `${entry.display_name || "研究員"}のロボ`;
      img.loading = "lazy";
      img.width = 32;
      img.height = 32;
      wrap.appendChild(img);
      iconsNode.appendChild(wrap);
    });
    const extra = Math.max(0, Number(count || 0) - Math.min(entries.length, 8));
    if (extra > 0) {
      const more = document.createElement("span");
      more.className = "presence-avatar-more";
      more.textContent = `+${extra}`;
      iconsNode.appendChild(more);
    }
  };

  const renderList = (entries) => {
    if (!listNode) return;
    clearChildren(listNode);
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "presence-empty";
      empty.textContent = "まだ参加研究員はいません";
      listNode.appendChild(empty);
      return;
    }
    entries.forEach((entry) => {
      const card = document.createElement("article");
      card.className = `presence-member-card is-${entry.tone || "idle"}`;

      const visual = document.createElement("div");
      visual.className = "presence-member-visual";
      const robot = document.createElement("img");
      robot.className = "presence-member-robot";
      robot.src = entry.robot_icon_32_url || "";
      robot.alt = `${entry.display_name || "研究員"}のロボ`;
      robot.loading = "lazy";
      robot.width = 48;
      robot.height = 48;
      const avatar = document.createElement("img");
      avatar.className = "presence-member-avatar";
      avatar.src = entry.avatar_url || "";
      avatar.alt = "";
      avatar.loading = "lazy";
      avatar.width = 20;
      avatar.height = 20;
      visual.appendChild(robot);
      visual.appendChild(avatar);

      const meta = document.createElement("div");
      meta.className = "presence-member-meta";
      const name = document.createElement("div");
      name.className = "presence-member-name";
      name.textContent = entry.display_name || "研究員";
      const state = document.createElement("div");
      state.className = "presence-member-state";
      state.textContent = entry.state_label || "探索待機中";
      const time = document.createElement("div");
      time.className = "presence-member-time";
      time.textContent = entry.minutes_ago_label || "たった今";
      meta.appendChild(name);
      meta.appendChild(state);
      meta.appendChild(time);

      card.appendChild(visual);
      card.appendChild(meta);
      listNode.appendChild(card);
    });
  };

  const applyPayload = (payload) => {
    if (!payload || payload.ok !== true) return;
    const count = Number(payload.count || 0);
    const within = Number(payload.within_minutes || 20);
    const entries = Array.isArray(payload.entries) ? payload.entries : [];
    setText(titleNode, count > 0 ? `研究員 ${count}名 参加中` : "今は静かです");
    setText(subtitleNode, count > 0 ? `最近${within}分で動いた研究員` : "最初の研究員になってみましょう");
    renderIcons(entries, count);
    renderList(entries);
  };

  const refresh = async (limit) => {
    if (!apiUrl) return;
    try {
      const resp = await fetch(buildUrl(limit), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) return;
      applyPayload(await resp.json());
    } catch (_err) {
      // Presence is ambient UI; failures should not disturb home.
    }
  };

  const openModal = () => {
    if (!modal) return;
    isModalOpen = true;
    modal.hidden = false;
    refresh(modalLimit);
  };

  const closeModal = () => {
    if (!modal) return;
    isModalOpen = false;
    modal.hidden = true;
  };

  if (openBtn) openBtn.addEventListener("click", openModal);
  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (modal) {
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) closeModal();
    });
  }
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && isModalOpen) closeModal();
  });

  const start = () => {
    if (timerId !== null) window.clearInterval(timerId);
    timerId = window.setInterval(() => refresh(isModalOpen ? modalLimit : 8), 30000);
  };
  const stop = () => {
    if (timerId !== null) {
      window.clearInterval(timerId);
      timerId = null;
    }
  };
  start();
  window.addEventListener("pagehide", stop);
  window.addEventListener("pageshow", start);
})();

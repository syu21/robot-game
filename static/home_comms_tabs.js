(() => {
  const HASH_PREFIX = "#home-comms-";
  const SCROLL_STORAGE_KEY = "home-comms-scroll";

  const isHomePage = () => !!(document.body && document.body.classList.contains("home-page"));

  const parseHashState = (hashValue, defaultTab, defaultRoom) => {
    const hash = String(hashValue || "").trim();
    if (!hash.startsWith(HASH_PREFIX)) {
      return { tab: defaultTab, room: defaultRoom, shouldFocusPanel: false };
    }
    if (hash === "#home-comms-world") {
      return { tab: "world", room: defaultRoom, shouldFocusPanel: true };
    }
    if (hash === "#home-comms-faction") {
      return { tab: "faction", room: defaultRoom, shouldFocusPanel: true };
    }
    if (hash === "#home-comms-personal") {
      return { tab: "personal", room: defaultRoom, shouldFocusPanel: true };
    }
    if (hash.startsWith("#home-comms-rooms")) {
      const rawRoom = hash.replace("#home-comms-rooms", "").replace(/^-/, "").trim();
      return {
        tab: "rooms",
        room: rawRoom || defaultRoom,
        shouldFocusPanel: true,
      };
    }
    return { tab: defaultTab, room: defaultRoom, shouldFocusPanel: false };
  };

  const buildHash = (tabKey, roomKey, defaultRoom) => {
    if (tabKey === "rooms") {
      return `#home-comms-rooms-${roomKey || defaultRoom}`;
    }
    return `#home-comms-${tabKey || "world"}`;
  };

  const restoreStoredScroll = () => {
    try {
      const raw = window.sessionStorage.getItem(SCROLL_STORAGE_KEY);
      if (!raw) {
        return false;
      }
      window.sessionStorage.removeItem(SCROLL_STORAGE_KEY);
      const payload = JSON.parse(raw);
      const x = Number(payload && payload.x);
      const y = Number(payload && payload.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        return false;
      }
      window.requestAnimationFrame(() => {
        window.scrollTo(x, y);
      });
      return true;
    } catch (_err) {
      return false;
    }
  };

  const rememberScrollBeforeReload = () => {
    try {
      window.sessionStorage.setItem(
        SCROLL_STORAGE_KEY,
        JSON.stringify({
          x: window.scrollX || 0,
          y: window.scrollY || 0,
        }),
      );
    } catch (_err) {
      // no-op
    }
  };

  const initHomeCommsTabs = () => {
    if (!isHomePage()) {
      return;
    }

    const root = document.querySelector("[data-home-comms-root='1']");
    if (!root) {
      return;
    }

    const defaultTab = String(root.getAttribute("data-home-comms-initial-tab") || "world");
    const defaultRoom = String(root.getAttribute("data-home-comms-initial-room") || "global_room");
    const tabButtons = Array.from(root.querySelectorAll("[data-home-comms-tab-button]"));
    const panes = Array.from(root.querySelectorAll("[data-home-comms-pane]"));
    const roomButtons = Array.from(root.querySelectorAll("[data-home-comms-room-button]"));
    const roomPanes = Array.from(root.querySelectorAll("[data-home-comms-room-pane]"));

    let activeTab = defaultTab;
    let activeRoom = defaultRoom;
    let resizeFrame = 0;

    const textNode = (value) => document.createTextNode(String(value || ""));

    const renderMessageItem = (item) => {
      const article = document.createElement("article");
      article.className = "card home-comms-item comms-message-card";

      const head = document.createElement("div");
      head.className = "comms-message-head";
      const user = document.createElement("div");
      user.className = "presence-user-line";
      const meta = document.createElement("div");
      meta.className = "user-signal-meta";
      const name = document.createElement("div");
      name.className = "feed-user user-signal-name";
      name.appendChild(textNode(item.user_label || "unknown"));
      const presence = document.createElement("div");
      presence.className = "presence-mini-label";
      presence.appendChild(textNode(item.presence_label || "探索待機中"));
      meta.append(name, presence);
      user.appendChild(meta);
      const time = document.createElement("div");
      time.className = "feed-time";
      time.appendChild(textNode(item.time_jst || ""));
      head.append(user, time);

      const body = document.createElement("div");
      body.className = "comms-message-body";
      body.appendChild(textNode(item.message || ""));
      article.append(head, body);
      return article;
    };

    const renderPersonalItem = (item) => {
      const article = document.createElement("article");
      article.className = `card feed-card home-comms-item comms-personal-card feed-card-${item.accent || "default"}`;
      const head = document.createElement("div");
      head.className = "feed-kicker-row";
      const title = document.createElement("div");
      title.className = "feed-kicker";
      title.appendChild(textNode(item.title || ""));
      const time = document.createElement("div");
      time.className = "feed-time";
      time.appendChild(textNode(item.time_jst || ""));
      head.append(title, time);
      const body = document.createElement("div");
      body.className = "feed-text";
      body.appendChild(textNode(item.text || ""));
      article.append(head, body);
      (item.meta_lines || []).forEach((line) => {
        const meta = document.createElement("div");
        meta.className = "feed-meta";
        meta.appendChild(textNode(line));
        article.appendChild(meta);
      });
      return article;
    };

    const renderEmpty = (text) => {
      const empty = document.createElement("div");
      empty.className = "home-mini-log-empty";
      empty.appendChild(textNode(text || "まだ表示できるログがありません。"));
      return empty;
    };

    const loadPanePreview = async (pane) => {
      if (!pane || pane.getAttribute("data-home-comms-loaded") === "1") {
        return;
      }
      const url = pane.getAttribute("data-home-comms-source-url");
      const list = pane.querySelector("[data-home-comms-scroll-list='1']");
      if (!url || !list) {
        pane.setAttribute("data-home-comms-loaded", "1");
        return;
      }
      try {
        const resp = await fetch(url, {
          headers: { "Accept": "application/json" },
          credentials: "same-origin",
        });
        if (!resp.ok) {
          return;
        }
        const payload = await resp.json();
        if (!payload || payload.ok !== true) {
          return;
        }
        list.replaceChildren();
        const items = Array.isArray(payload.items) ? payload.items : [];
        if (items.length <= 0) {
          list.appendChild(renderEmpty(payload.empty_text));
        } else {
          items.forEach((item) => {
            list.appendChild(item.kind === "personal" ? renderPersonalItem(item) : renderMessageItem(item));
          });
        }
        if (payload.activity_line) {
          const activity = pane.querySelector(".presence-mini-label");
          if (activity) {
            activity.textContent = payload.activity_line;
          }
        }
        pane.setAttribute("data-home-comms-loaded", "1");
        scheduleListResize();
      } catch (_err) {
        // Keep the static fallback/link available when preview fetch fails.
      }
    };

    const resizeScrollableLists = () => {
      const lists = Array.from(root.querySelectorAll("[data-home-comms-scroll-list='1']"));
      lists.forEach((list) => {
        const maxVisible = Math.max(1, Number.parseInt(list.getAttribute("data-home-comms-max-visible") || "5", 10) || 5);
        const visibleItems = Array.from(list.children).filter((child) => !!(child.offsetParent || child.getClientRects().length));
        list.classList.toggle("is-scrollable", visibleItems.length > maxVisible);
      });
    };

    const scheduleListResize = () => {
      if (resizeFrame) {
        window.cancelAnimationFrame(resizeFrame);
      }
      resizeFrame = window.requestAnimationFrame(() => {
        resizeFrame = 0;
        resizeScrollableLists();
      });
    };

    const dispatchChange = () => {
      root.dispatchEvent(
        new CustomEvent("home-comms:tabchange", {
          detail: {
            tab: activeTab,
            room: activeRoom,
          },
        }),
      );
    };

    const syncHash = () => {
      const nextHash = buildHash(activeTab, activeRoom, defaultRoom);
      if (window.location.hash === nextHash) {
        return;
      }
      const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;
      window.history.replaceState(null, "", nextUrl);
    };

    const setRoom = (roomKey, options) => {
      const opts = options || {};
      activeRoom = roomKey || defaultRoom;
      roomButtons.forEach((button) => {
        const isActive = button.getAttribute("data-home-comms-room-button") === activeRoom;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
      });
      roomPanes.forEach((pane) => {
        const isActive = pane.getAttribute("data-home-comms-room-pane") === activeRoom;
        pane.classList.toggle("is-active", isActive);
        pane.hidden = !isActive;
        pane.setAttribute("aria-hidden", isActive ? "false" : "true");
      });
      if (opts.syncHash !== false && activeTab === "rooms") {
        syncHash();
      }
      scheduleListResize();
      if (opts.dispatch !== false) {
        dispatchChange();
      }
      const activePane = roomPanes.find((pane) => pane.getAttribute("data-home-comms-room-pane") === activeRoom);
      loadPanePreview(activePane);
    };

    const setTab = (tabKey, options) => {
      const opts = options || {};
      activeTab = tabKey || defaultTab;
      tabButtons.forEach((button) => {
        const isActive = button.getAttribute("data-home-comms-tab-button") === activeTab;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
      });
      panes.forEach((pane) => {
        const isActive = pane.getAttribute("data-home-comms-pane") === activeTab;
        pane.classList.toggle("is-active", isActive);
        pane.hidden = !isActive;
        pane.setAttribute("aria-hidden", isActive ? "false" : "true");
      });
      if (activeTab === "rooms") {
        setRoom(opts.room || activeRoom || defaultRoom, { syncHash: false, dispatch: false });
      }
      if (opts.syncHash !== false) {
        syncHash();
      }
      scheduleListResize();
      if (opts.dispatch !== false) {
        dispatchChange();
      }
      const activePane = panes.find((pane) => pane.getAttribute("data-home-comms-pane") === activeTab);
      loadPanePreview(activePane);
    };

    tabButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const tabKey = button.getAttribute("data-home-comms-tab-button") || defaultTab;
        if (tabKey === "rooms") {
          setTab("rooms", { room: activeRoom || defaultRoom });
          return;
        }
        setTab(tabKey);
      });
    });

    roomButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const roomKey = button.getAttribute("data-home-comms-room-button") || defaultRoom;
        if (activeTab !== "rooms") {
          setTab("rooms", { room: roomKey, syncHash: false, dispatch: false });
        }
        setRoom(roomKey);
      });
    });

    root.querySelectorAll("[data-home-comms-submit='1']").forEach((form) => {
      form.addEventListener("submit", rememberScrollBeforeReload);
    });
    window.addEventListener("resize", scheduleListResize);

    window.addEventListener("hashchange", () => {
      const parsed = parseHashState(window.location.hash, defaultTab, defaultRoom);
      setTab(parsed.tab, { room: parsed.room, syncHash: false, dispatch: true });
      if (parsed.tab === "rooms") {
        setRoom(parsed.room, { syncHash: false, dispatch: false });
      }
    });

    const parsed = parseHashState(window.location.hash, defaultTab, defaultRoom);
    const restored = restoreStoredScroll();
    setTab(parsed.tab, { room: parsed.room, syncHash: false, dispatch: false });
    if (parsed.tab === "rooms") {
      setRoom(parsed.room, { syncHash: false, dispatch: false });
    }
    if (parsed.shouldFocusPanel && !restored) {
      window.requestAnimationFrame(() => {
        root.scrollIntoView({ block: "start" });
      });
    }
    scheduleListResize();
    dispatchChange();
  };

  document.addEventListener("DOMContentLoaded", initHomeCommsTabs);
})();

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

    const resizeScrollableLists = () => {
      const lists = Array.from(root.querySelectorAll("[data-home-comms-scroll-list='1']"));
      lists.forEach((list) => {
        const maxVisible = Math.max(1, Number.parseInt(list.getAttribute("data-home-comms-max-visible") || "5", 10) || 5);
        const visibleItems = Array.from(list.children).filter((child) => !!(child.offsetParent || child.getClientRects().length));
        if (visibleItems.length <= maxVisible) {
          list.style.maxHeight = "";
          list.classList.remove("is-scrollable");
          return;
        }
        const listStyle = window.getComputedStyle(list);
        const gap = Number.parseFloat(listStyle.rowGap || listStyle.gap || "0") || 0;
        let height = 0;
        visibleItems.slice(0, maxVisible).forEach((child, index) => {
          height += child.getBoundingClientRect().height;
          if (index > 0) {
            height += gap;
          }
        });
        if (height > 0) {
          list.style.maxHeight = `${Math.ceil(height)}px`;
          list.classList.add("is-scrollable");
        }
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

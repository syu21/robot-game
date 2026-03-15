(() => {
  const diag = window.__clientDiag || null;
  const markStep = (step, extra) => {
    try {
      if (diag && typeof diag.step === "function") {
        diag.step(step, extra || null);
      }
    } catch (_err) {
      // no-op
    }
  };
  markStep("header_scroll:start");

  const header = document.getElementById("site-header");
  if (!header) {
    markStep("header_scroll:skip-no-header");
    return;
  }
  let lastY = window.scrollY || 0;
  const hideThreshold = 40;
  const showThreshold = 20;
  const directionThreshold = 8;
  let hidden = false;
  let ticking = false;

  function setHeaderOffset() {
    const h = Math.max(0, Math.round(header.getBoundingClientRect().height));
    document.documentElement.style.setProperty("--site-header-height", `${h}px`);
  }

  function setHidden(nextHidden) {
    if (hidden === nextHidden) return;
    hidden = nextHidden;
    header.classList.toggle("is-hidden", hidden);
  }

  function update() {
    const y = window.scrollY || 0;
    const dy = y - lastY;
    if (y <= showThreshold) {
      setHidden(false);
    } else if (hidden) {
      if (dy < -directionThreshold) {
        setHidden(false);
      }
    } else if (y >= hideThreshold && dy > directionThreshold) {
      setHidden(true);
    }
    lastY = y;
    ticking = false;
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(update);
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", setHeaderOffset, { passive: true });
  window.addEventListener("pageshow", () => {
    setHeaderOffset();
    lastY = window.scrollY || 0;
    if (lastY <= showThreshold) setHidden(false);
  });
  setHeaderOffset();
  setHidden(false);
  markStep("header_scroll:done");
})();

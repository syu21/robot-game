(function () {
  if (window.__uiProbeLoaded) return;
  window.__uiProbeLoaded = true;

  document.addEventListener("DOMContentLoaded", () => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("probe") !== "1") return;
    if (window.__uiProbeBound) return;
    window.__uiProbeBound = true;

    const logTopLeft = (eventName) => {
      const el = document.elementFromPoint(10, 10);
      if (!el) {
        console.log("[probe]", eventName, "top-left", null);
        return;
      }
      const style = window.getComputedStyle(el);
      console.log("[probe]", eventName, "top-left", el);
      console.log("[probe] style", {
        position: style.position,
        zIndex: style.zIndex,
        width: style.width,
        height: style.height,
        opacity: style.opacity,
        background: style.background,
        filter: style.filter,
        backdropFilter: style.backdropFilter,
        pointerEvents: style.pointerEvents,
      });
    };

    let scrollTicking = false;
    window.addEventListener(
      "scroll",
      () => {
        if (scrollTicking) return;
        scrollTicking = true;
        window.requestAnimationFrame(() => {
          logTopLeft("scroll");
          scrollTicking = false;
        });
      },
      { passive: true }
    );
    window.addEventListener("click", () => logTopLeft("click"));

    console.log("[probe] enabled: ?probe=1");
    logTopLeft("init");
  });
})();

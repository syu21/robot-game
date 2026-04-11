(() => {
  const form = document.querySelector("[data-lab-stat-form]");
  if (!form) return;

  const maxTotal = Number(form.dataset.maxTotal || "36");
  const selects = Array.from(form.querySelectorAll("[data-lab-stat-select]"));
  const totalBox = form.querySelector("[data-lab-stat-total]");
  const submitButton = form.querySelector("[data-lab-submit]");
  const polygon = form.querySelector("[data-lab-radar-polygon]");
  const dots = Array.from(form.querySelectorAll("[data-lab-radar-dot]"));
  const center = 100;
  const radius = 70;

  const radarPoint = (value, index) => {
    const angle = -Math.PI / 2 + index * ((Math.PI * 2) / selects.length);
    const scale = Math.max(0.1, Math.min(1, Number(value || "1") / 10));
    const x = center + Math.cos(angle) * radius * scale;
    const y = center + Math.sin(angle) * radius * scale;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };

  const updateTotal = () => {
    const values = selects.map((select) => Number(select.value || "0"));
    const total = values.reduce((sum, value) => sum + value, 0);

    if (totalBox) {
      totalBox.textContent = `現在合計: ${total} / ${maxTotal}`;
      totalBox.classList.toggle("is-over", total > maxTotal);
    }

    if (polygon) {
      const points = values.map((value, index) => radarPoint(value, index));
      polygon.setAttribute("points", points.join(" "));
      dots.forEach((dot, index) => {
        const point = points[index];
        if (!point) return;
        const [x, y] = point.split(",");
        dot.setAttribute("cx", x);
        dot.setAttribute("cy", y);
      });
    }

    if (submitButton) {
      submitButton.disabled = total > maxTotal;
    }
  };

  selects.forEach((select) => {
    select.addEventListener("change", updateTotal);
    select.addEventListener("input", updateTotal);
  });
  updateTotal();
})();

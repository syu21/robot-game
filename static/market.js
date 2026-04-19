(function () {
  const formEl = document.getElementById("marketSellForm");
  const checks = Array.from(document.querySelectorAll("[data-market-sell-checkbox]"));
  const countEl = document.getElementById("marketSellCount");
  const totalEl = document.getElementById("marketSellTotal");
  const namesEl = document.getElementById("marketSellNames");
  const submitEl = document.getElementById("marketSellSubmit");
  const clearEl = document.getElementById("marketSellClear");
  if (!checks.length || !countEl || !totalEl || !namesEl || !submitEl) return;

  function updateSummary() {
    const selected = checks.filter((item) => item.checked);
    const total = selected.reduce((sum, item) => sum + Number(item.dataset.sellValue || 0), 0);
    countEl.textContent = String(selected.length);
    totalEl.textContent = String(total);
    submitEl.disabled = false;
    submitEl.dataset.emptySelection = selected.length === 0 ? "1" : "0";
    namesEl.innerHTML = "";
    if (!selected.length) {
      const li = document.createElement("li");
      li.textContent = "まだ選択されていません";
      namesEl.appendChild(li);
      return;
    }
    selected.slice(0, 3).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item.dataset.sellName || "パーツ";
      namesEl.appendChild(li);
    });
    if (selected.length > 3) {
      const li = document.createElement("li");
      li.textContent = "ほか " + String(selected.length - 3) + "件";
      namesEl.appendChild(li);
    }
  }

  checks.forEach((item) => {
    item.addEventListener("change", updateSummary);
    item.addEventListener("input", updateSummary);
    item.addEventListener("click", function () {
      window.setTimeout(updateSummary, 0);
    });
  });
  if (formEl) {
    formEl.addEventListener("change", updateSummary);
    formEl.addEventListener("input", updateSummary);
  }
  if (clearEl) {
    clearEl.addEventListener("click", function () {
      checks.forEach((item) => {
        item.checked = false;
      });
      updateSummary();
    });
  }
  updateSummary();
  window.requestAnimationFrame(updateSummary);
  window.setTimeout(updateSummary, 0);
  window.setTimeout(updateSummary, 150);
  window.addEventListener("pageshow", updateSummary);
})();

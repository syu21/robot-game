(function () {
  function updateSquadForm(form) {
    var boxes = Array.prototype.slice.call(form.querySelectorAll("[data-tower-robot-checkbox]"));
    var checked = boxes.filter(function (box) {
      return box.checked;
    });
    boxes.forEach(function (box) {
      if (!box.checked) box.disabled = checked.length >= 3;
      var card = box.closest(".tower-robot-card");
      var label = card ? card.querySelector("[data-tower-select-label]") : null;
      var status = card ? card.querySelector("[data-tower-select-status]") : null;
      if (card) card.classList.toggle("is-selected", box.checked);
      if (label) label.textContent = box.checked ? "選択済み" : "小隊に選ぶ";
      if (status) status.textContent = box.checked ? "選択中" : "出撃可能";
    });
    checked.forEach(function (box, index) {
      box.name = "robot_" + (index + 1);
    });
    var count = form.querySelector("[data-tower-selected-count]");
    if (count) count.textContent = String(checked.length);
    var startButton = form.querySelector("[data-tower-start-button]");
    if (startButton) startButton.disabled = checked.length !== 3;
  }

  function initTowerSquadForms() {
    document.querySelectorAll("[data-tower-squad-form]").forEach(function (form) {
      updateSquadForm(form);
      form.addEventListener("change", function (event) {
        if (!event.target.matches("[data-tower-robot-checkbox]")) return;
        updateSquadForm(form);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTowerSquadForms);
  } else {
    initTowerSquadForms();
  }
})();

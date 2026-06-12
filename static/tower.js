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

  function initTowerBattleReplay() {
    document.querySelectorAll("[data-tower-battle-replay]").forEach(function (root) {
      var prefersReducedMotion =
        window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      var logs = Array.prototype.slice.call(root.querySelectorAll("[data-tower-log-line]"));
      var actions = root.querySelector("[data-tower-replay-actions]");
      var banner = root.querySelector("[data-tower-result-banner]");
      var status = root.querySelector("[data-tower-replay-status]");
      var caption = root.querySelector("[data-tower-replay-caption]");
      var projectile = root.querySelector("[data-tower-replay-projectile]");
      var player = root.querySelector('[data-tower-replay-unit="player"]');
      var enemy = root.querySelector('[data-tower-replay-unit="enemy"]');
      var hpMeters = {
        player: root.querySelector('[data-tower-hp-meter="player"]'),
        enemy: root.querySelector('[data-tower-hp-meter="enemy"]')
      };
      var hpTexts = {
        player: root.querySelector('[data-tower-hp-text="player"]'),
        enemy: root.querySelector('[data-tower-hp-text="enemy"]')
      };
      var timers = [];
      var finished = false;

      function setStatus(text) {
        if (status) status.textContent = text;
      }

      function setCaption(text) {
        if (caption) caption.textContent = text;
      }

      function clearMotionClasses() {
        [player, enemy, projectile].forEach(function (el) {
          if (!el) return;
          el.classList.remove(
            "is-attacking",
            "is-hit",
            "is-player-shot",
            "is-enemy-shot",
            "is-active"
          );
        });
      }

      function setHp(side, value) {
        var meter = hpMeters[side];
        var text = hpTexts[side];
        if (!meter) return;
        var max = Math.max(1, Number(meter.max || 1));
        var next = Math.max(0, Math.min(max, Number(value || 0)));
        meter.value = next;
        if (text) text.textContent = String(Math.round(next));
      }

      function setFinalHp(side) {
        var meter = hpMeters[side];
        if (!meter) return;
        setHp(side, Number(meter.dataset.finalValue || 0));
      }

      function revealAll() {
        finished = true;
        timers.forEach(window.clearTimeout);
        clearMotionClasses();
        setFinalHp("player");
        setFinalHp("enemy");
        root.classList.remove("is-replay-pending", "is-replaying");
        root.classList.add("is-replay-complete");
        logs.forEach(function (line) {
          line.classList.add("is-visible");
        });
        if (banner) banner.classList.add("is-visible");
        if (actions) actions.classList.add("is-visible");
        setStatus(status ? status.dataset.finalStatus || status.textContent : "");
        setCaption("戦闘終了");
      }

      function schedule(delay, callback) {
        timers.push(window.setTimeout(callback, delay));
      }

      function playStep(line, index) {
        if (finished) return;
        clearMotionClasses();
        var text = line ? line.textContent || "" : "";
        var enemyTurn = text.indexOf("反撃") !== -1 || text.indexOf("ロボに") !== -1;
        var attacker = enemyTurn ? enemy : player;
        var defender = enemyTurn ? player : enemy;
        var shotClass = enemyTurn ? "is-enemy-shot" : "is-player-shot";
        setStatus((index + 1) + " / " + logs.length);
        setCaption(text || "交戦中");
        if (attacker) attacker.classList.add("is-attacking");
        if (projectile) {
          projectile.classList.add("is-active", shotClass);
        }
        schedule(180, function () {
          if (defender) defender.classList.add("is-hit");
          setFinalHp(enemyTurn ? "player" : "enemy");
        });
        schedule(260, function () {
          if (line) line.classList.add("is-visible");
        });
      }

      if (!logs.length || prefersReducedMotion) {
        revealAll();
        return;
      }

      root.classList.remove("is-replay-pending");
      root.classList.add("is-replaying");
      setStatus("交戦中");
      setCaption("交戦開始");

      schedule(420, function () {
        logs.forEach(function (line, index) {
          schedule(index * 760, function () {
            playStep(line, index);
          });
        });
        schedule(logs.length * 760 + 420, revealAll);
      });

      root.addEventListener("click", function (event) {
        if (event.target.closest("a, button, input, label")) return;
        if (!finished) revealAll();
      });
      window.addEventListener("pagehide", revealAll, { once: true });
    });
  }

  function initTower() {
    initTowerSquadForms();
    initTowerBattleReplay();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTower);
  } else {
    initTower();
  }
})();

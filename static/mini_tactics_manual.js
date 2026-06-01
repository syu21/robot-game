(function () {
  var root = document.getElementById("miniTacticsManual");
  if (!root) return;

  function readJsonData(name, fallback) {
    var raw = root.dataset[name];
    if (raw === undefined || raw === null || raw === "") return fallback;
    try {
      return JSON.parse(raw);
    } catch (error) {
      return fallback;
    }
  }

  var boardState = readJsonData("boardState", {});
  var isMiniAnimalShogi = readJsonData("isMiniAnimalShogi", false);
  var isMiniShogi = readJsonData("isMiniShogi", false);
  var previousBoardState = readJsonData("previousBoardState", null);
  var currentBoardState = readJsonData("currentBoardState", null);
  var actionSequence = readJsonData("actionSequence", []);
  var optionsByUnit = readJsonData("optionsByUnit", {});
  var capsuleOptions = readJsonData("capsuleOptions", {});
  var zocCells = readJsonData("zocCells", []);
  var threatCells = readJsonData("threatCells", []);
  var unitAssets = readJsonData("unitAssets", {});
  var playableSide = readJsonData("playableSide", "ally");
  var canAct = readJsonData("canAct", true);
  var isOnlineBattle = readJsonData("isOnlineBattle", false);
  var stateUrl = readJsonData("stateUrl", "");
  var turnMessage = readJsonData("turnMessage", "");
  var lastKnownUpdatedAt = readJsonData("updatedAt", 0);
  var battleId = readJsonData("battleId", "");
  var openingSequencePending = readJsonData("openingSequencePending", false);
  var board = document.getElementById("miniTacticsManualBoard");
  var bannerEl = document.getElementById("miniTacticsPhaseBanner");
  var captionEl = document.getElementById("miniTacticsActionCaption");
  var selectedEl = document.getElementById("miniTacticsManualSelected");
  var hintEl = document.getElementById("miniTacticsManualHint");
  var replayButton = document.getElementById("manualReplayButton");
  var skipReplayButton = document.getElementById("manualSkipReplayButton");
  var actorInput = document.getElementById("manualActorUnitId");
  var actionTypeInput = document.getElementById("manualActionType");
  var toXInput = document.getElementById("manualToX");
  var toYInput = document.getElementById("manualToY");
  var moveXInput = document.getElementById("manualMoveX");
  var moveYInput = document.getElementById("manualMoveY");
  var targetInput = document.getElementById("manualTargetUnitId");
  var pieceTypeInput = document.getElementById("manualPieceType");
  var submit = document.getElementById("manualSubmit");
  var openingEl = document.getElementById("miniShogiOpening");
  var openingSkip = document.getElementById("miniShogiOpeningSkip");
  if (!board) return;

  var selectedUnitId = "";
  var selectedCapsulePiece = "";
  var selectedActionMode = "none";
  var selectedMove = null;
  var replaying = false;
  var actionPending = false;
  var replayToken = 0;

  function unitById(unitId) {
    return (boardState.units || []).find(function (unit) { return String(unit.unit_id) === String(unitId); });
  }

  function sameCell(a, b) {
    return Number(a.x) === Number(b.x) && Number(a.y) === Number(b.y);
  }

  function clearMarks() {
    board.querySelectorAll(".mini-tactics-cell").forEach(function (cell) {
      cell.classList.remove("is-move-option", "is-attack-option", "is-target-option", "is-selected-move", "is-danger-move", "is-deploy-option");
    });
    board.querySelectorAll(".mini-tactics-unit").forEach(function (unit) {
      unit.classList.remove("is-selected");
    });
    document.querySelectorAll("[data-capsule-piece]").forEach(function (button) {
      button.classList.remove("is-selected");
    });
  }

  function sleep(ms) {
    return new Promise(function (resolve) { window.setTimeout(resolve, ms); });
  }

  function addClasses(el, classes) {
    if (!el) return;
    String(classes || "").split(/\s+/).filter(Boolean).forEach(function (className) {
      el.classList.add(className);
    });
  }

  function removeClasses(el, classes) {
    if (!el) return;
    String(classes || "").split(/\s+/).filter(Boolean).forEach(function (className) {
      el.classList.remove(className);
    });
  }

  function setActionEnabled(enabled) {
    if (submit) submit.disabled = !enabled || !actorInput.value;
    if (replaying && submit) submit.disabled = true;
  }

  function setControlsLocked(locked) {
    if (board) board.classList.toggle("is-locked", !!locked);
    if (replayButton) replayButton.disabled = !!locked;
  }

  function finalBoardStateFromResponse(data) {
    if (!data || !data.board_state) return null;
    return data.board_state.current_board_state || data.board_state;
  }

  function syncActionData(data) {
    var finalState = finalBoardStateFromResponse(data);
    previousBoardState = data && data.board_state ? data.board_state.previous_board_state || null : null;
    currentBoardState = finalState;
    actionSequence = (data && data.action_sequence) || [];
    optionsByUnit = (data && data.options_by_unit) || {};
    capsuleOptions = (data && (data.capsule_options || (finalState && finalState.capsule_options))) || {};
    zocCells = (data && data.zoc_cells) || [];
    threatCells = (data && data.threat_cells) || [];
    if (data && data.turn_message) turnMessage = data.turn_message;
    if (data && typeof data.can_act !== "undefined") canAct = !!data.can_act;
    if (data && typeof data.updated_at !== "undefined") lastKnownUpdatedAt = data.updated_at || lastKnownUpdatedAt;
    selectedUnitId = "";
    selectedCapsulePiece = "";
    selectedActionMode = "none";
    selectedMove = null;
    clearMarks();
    return finalState;
  }

  async function postImmediateAction(actionType, payload) {
    if (!isMiniShogi || replaying || actionPending || boardState.result) return;
    if (actionType !== "deploy_capsule" && !selectedUnitId) return;
    actorInput.value = actionType === "deploy_capsule" ? "" : selectedUnitId;
    actionTypeInput.value = actionType;
    targetInput.value = payload.target_unit_id || "";
    if (pieceTypeInput) pieceTypeInput.value = payload.piece_type || "";
    toXInput.value = payload.to_x != null ? String(payload.to_x) : "";
    toYInput.value = payload.to_y != null ? String(payload.to_y) : "";
    moveXInput.value = payload.to_x != null ? String(payload.to_x) : "";
    moveYInput.value = payload.to_y != null ? String(payload.to_y) : "";
    setCaption("行動を送信中", "ally");
    setControlsLocked(true);
    if (!isMiniAnimalShogi) {
      document.getElementById("miniTacticsManualAction").submit();
      return;
    }
    actionPending = true;
    try {
      var response = await fetch(document.getElementById("miniTacticsManualAction").action, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-Requested-With": "fetch"
        },
        body: JSON.stringify({
          actor_unit_id: actionType === "deploy_capsule" ? "" : selectedUnitId,
          action_type: actionType,
          piece_type: payload.piece_type || "",
          to_x: payload.to_x,
          to_y: payload.to_y,
          target_unit_id: payload.target_unit_id || ""
        })
      });
      var data = await response.json().catch(function () { return null; });
      if (!response.ok || !data || !data.ok) {
        throw new Error((data && data.error) || "行動できませんでした。");
      }
      var finalState = syncActionData(data);
      if (actionSequence.length && previousBoardState && currentBoardState) {
        await playSequence();
      } else if (finalState) {
        boardState = finalState;
        renderBoard(boardState);
        setCaption(boardState.result ? "決着" : (turnMessage || "味方ターン：動かすミニロボを選択"), boardState.result ? "result" : (canAct ? "ally" : "enemy"));
      }
      if (selectedEl) selectedEl.textContent = "味方ユニットを選択";
      if (hintEl) hintEl.textContent = data.message || "";
      maybeStartPolling();
    } catch (error) {
      if (hintEl) hintEl.textContent = error && error.message ? error.message : "通信エラーが発生しました。";
      setCaption("味方ターン：動かすミニロボを選択", "ally");
      setControlsLocked(false);
    } finally {
      actionPending = false;
      if (!replaying) {
        setControlsLocked(false);
        renderCapsules(boardState);
      }
    }
  }

  function unitLabel(unit) {
    return String((unit && unit.name) || "?").slice(0, 3);
  }

  function staticAssetUrl(path) {
    var rel = String(path || "").replace(/^\/+/, "");
    if (!rel) return "";
    if (/^https?:\/\//.test(rel) || rel.indexOf("/static/") === 0) return rel;
    return "/static/" + rel;
  }

  function imageUrlForUnit(unit) {
    if (!unit) return "";
    return unitAssets[String(unit.unit_id || "")]
      || unit.image_url
      || staticAssetUrl(unit.image_path)
      || staticAssetUrl(unit.species_key ? "mini_robots/" + unit.species_key + "/normal.png" : "");
  }

  function renderBoard(state) {
    board.querySelectorAll(".mini-tactics-unit").forEach(function (unitEl) { unitEl.remove(); });
    board.querySelectorAll(".mini-tactics-cell").forEach(function (cell) {
      cell.classList.remove("is-zoc", "is-threat", "is-move-option", "is-attack-option", "is-target-option", "is-selected-move", "is-danger-move", "is-deploy-option");
    });
    (state.units || []).forEach(function (unit) {
      if (unit.defeated) return;
      var cell = board.querySelector('[data-x="' + unit.x + '"][data-y="' + unit.y + '"]');
      if (!cell) return;
      var unitEl = document.createElement("span");
      unitEl.className = "mini-tactics-unit is-" + unit.side + (unit.unit_type === "core" ? " is-core" : "");
      if (unit.is_leader) unitEl.dataset.leader = "1";
      unitEl.dataset.unitId = unit.unit_id;
      unitEl.dataset.side = unit.side;
      unitEl.title = unit.name || "";
      var core = document.createElement("span");
      core.className = "mini-tactics-unit-core";
      var unitImageUrl = imageUrlForUnit(unit);
      if (unitImageUrl) {
        var img = document.createElement("img");
        img.src = unitImageUrl;
        img.alt = unit.name || "";
        img.loading = "lazy";
        core.appendChild(img);
      } else {
        core.textContent = unitLabel(unit);
      }
      unitEl.appendChild(core);
      if (unit.guarded) {
        var badge = document.createElement("span");
        badge.className = "mini-tactics-guard-badge";
        badge.textContent = "GUARD";
        unitEl.appendChild(badge);
      }
      if (unit.promoted) {
        var promotedBadge = document.createElement("span");
        promotedBadge.className = "mini-tactics-guard-badge";
        promotedBadge.textContent = "不死鳥";
        unitEl.appendChild(promotedBadge);
      }
      if (state.try_pending && state.try_pending.unit_id === unit.unit_id) {
        var tryBadge = document.createElement("span");
        tryBadge.className = "mini-tactics-guard-badge";
        tryBadge.textContent = "TRY";
        unitEl.appendChild(tryBadge);
      }
      cell.appendChild(unitEl);
    });
    markZoc();
    markThreats();
    renderCapsules(state);
  }

  function renderCapsules(state) {
    var capsules = (state && state.capsules) || {};
    var own = capsules[playableSide] || {};
    var otherSide = playableSide === "enemy" ? "ally" : "enemy";
    var other = capsules[otherSide] || {};
    document.querySelectorAll("[data-capsule-piece]").forEach(function (button) {
      var piece = button.dataset.pieceType || button.dataset.capsulePiece;
      var count = Number((own && own[piece]) || 0);
      var countEl = button.querySelector("[data-capsule-count]");
      if (countEl) countEl.textContent = String(count);
      button.disabled = !canAct || !!(state && state.result) || count <= 0 || replaying || actionPending;
      button.classList.toggle("is-empty", count <= 0);
      button.classList.toggle("is-available", count > 0);
      if (selectedCapsulePiece !== piece) button.classList.remove("is-selected");
    });
    document.querySelectorAll("[data-opponent-capsule-count]").forEach(function (el) {
      var piece = el.dataset.opponentCapsuleCount;
      var count = Number((other && other[piece]) || 0);
      el.textContent = String(count);
      var pieceEl = el.closest(".capsule-piece");
      if (pieceEl) {
        pieceEl.classList.toggle("is-empty", count <= 0);
        pieceEl.classList.toggle("is-available", count > 0);
      }
    });
  }

  function setCaption(text, phase) {
    if (captionEl) captionEl.textContent = text || "";
    if (bannerEl) {
      bannerEl.textContent = phase === "enemy" ? "ENEMY TURN" : (phase === "result" ? "RESULT" : "YOUR ACTION");
      bannerEl.dataset.phase = phase || "ally";
    }
  }

  function eventUnit(state, unitId) {
    return (state.units || []).find(function (unit) { return String(unit.unit_id) === String(unitId); });
  }

  function flashUnit(unitId, className) {
    var el = board.querySelector('[data-unit-id="' + unitId + '"]');
    if (!el) return;
    addClasses(el, className);
    window.setTimeout(function () { removeClasses(el, className); }, 420);
  }

  function flashCell(point, className) {
    if (!point) return;
    var cell = board.querySelector('[data-x="' + point.x + '"][data-y="' + point.y + '"]');
    if (!cell) return;
    addClasses(cell, className);
    window.setTimeout(function () { removeClasses(cell, className); }, 420);
  }

  async function playSequence() {
    if (!actionSequence || !actionSequence.length || !previousBoardState || !currentBoardState) {
      setCaption("味方ターン：動かすミニロボを選択", "ally");
      return;
    }
    var token = ++replayToken;
    replaying = true;
    setControlsLocked(true);
    if (submit) submit.disabled = true;
    var displayState = JSON.parse(JSON.stringify(previousBoardState));
    renderBoard(displayState);
    await sleep(260);
    for (var i = 0; i < actionSequence.length; i += 1) {
      if (token !== replayToken) return;
      var action = actionSequence[i];
      setCaption(action.text, action.phase || action.type);
      if (action.phase === "enemy") board.classList.add("is-enemy-turn");
      else board.classList.remove("is-enemy-turn");
      if (action.type === "move" || action.type === "move_capture") {
        var movingUnit = eventUnit(displayState, action.actor_unit_id);
        flashUnit(action.actor_unit_id, "is-animating-move");
        await sleep(180);
        if (movingUnit && action.to) {
          if (action.type === "move_capture") {
            var capturedUnit = eventUnit(displayState, action.target_unit_id);
            if (capturedUnit) capturedUnit.defeated = true;
          }
          movingUnit.x = action.to.x;
          movingUnit.y = action.to.y;
          renderBoard(displayState);
          flashUnit(action.actor_unit_id, "is-animating-move");
          if (action.type === "move_capture") flashCell(action.to, "is-impact-capture");
        }
      } else if (action.type === "attack") {
        var actor = eventUnit(displayState, action.actor_unit_id);
        var target = eventUnit(displayState, action.target_unit_id);
        flashUnit(action.actor_unit_id, "is-attacking is-weapon-" + (action.weapon_type || "melee"));
        flashUnit(action.target_unit_id, "is-hit");
        if (target) flashCell({x: target.x, y: target.y}, "is-impact-" + (action.weapon_type || "melee"));
        if (actor) flashCell({x: actor.x, y: actor.y}, "is-attack-origin");
      } else if (action.type === "defeated") {
        var defeated = eventUnit(displayState, action.actor_unit_id);
        flashUnit(action.actor_unit_id, "is-defeating");
        await sleep(180);
        if (defeated) defeated.defeated = true;
        renderBoard(displayState);
      } else if (action.type === "blocked") {
        flashUnit(action.actor_unit_id, "is-blocked");
        flashCell(action.to || action.at, "is-blocked-cell");
      } else if (action.type === "promote") {
        var promotedUnit = eventUnit(displayState, action.actor_unit_id);
        if (promotedUnit) {
          promotedUnit.promoted = true;
          promotedUnit.piece_type = "promoted_phoenix";
          promotedUnit.move_type = "promoted_phoenix";
          promotedUnit.name = promotedUnit.side === "enemy" ? "敵不死鳥" : "不死鳥";
          renderBoard(displayState);
        }
        flashUnit(action.actor_unit_id, "is-attacking");
      } else if (action.type === "reach_goal") {
        flashUnit(action.actor_unit_id, "is-attacking");
        if (action.result) displayState.result = action.result;
      } else if (action.type === "capsule_add") {
        var capsuleSide = action.phase === "enemy" ? "enemy" : "ally";
        displayState.capsules = displayState.capsules || {ally: {}, enemy: {}};
        displayState.capsules[capsuleSide] = displayState.capsules[capsuleSide] || {};
        displayState.capsules[capsuleSide][action.piece_type] = Number(displayState.capsules[capsuleSide][action.piece_type] || 0) + 1;
        renderCapsules(displayState);
      } else if (action.type === "deploy_capsule") {
        var deploySide = action.phase === "enemy" ? "enemy" : "ally";
        displayState.capsules = displayState.capsules || {ally: {}, enemy: {}};
        displayState.capsules[deploySide] = displayState.capsules[deploySide] || {};
        displayState.capsules[deploySide][action.piece_type] = Math.max(0, Number(displayState.capsules[deploySide][action.piece_type] || 0) - 1);
        if (action.piece_unit) {
          displayState.units = displayState.units || [];
          displayState.units.push(JSON.parse(JSON.stringify(action.piece_unit)));
        } else if (action.to && action.unit_id) {
          var deployName = action.name || (deploySide === "enemy" ? "敵" : "") + (action.piece_type === "phoenix" ? "フェニックス" : action.piece_type === "hydra" ? "ヒュドラ" : "スフィンクス");
          displayState.units = displayState.units || [];
          displayState.units.push({
            unit_id: action.unit_id,
            side: deploySide,
            is_leader: false,
            name: deployName,
            species_key: action.species_key || action.piece_type,
            x: action.to.x,
            y: action.to.y,
            piece_type: action.piece_type,
            move_type: action.move_type || action.piece_type,
            defeated: false,
            promoted: false,
            unit_type: "robot",
            image_path: action.image_path || "mini_robots/" + (action.species_key || action.piece_type) + "/normal.png"
          });
        }
        flashCell(action.to, "is-impact-capture");
        renderBoard(displayState);
      } else if (action.type === "wait") {
        flashUnit(action.actor_unit_id, "is-waiting");
      }
      await sleep(action.phase === "enemy" ? 560 : 460);
    }
    if (token !== replayToken) return;
    boardState = JSON.parse(JSON.stringify(currentBoardState));
    renderBoard(boardState);
    replaying = false;
    board.classList.remove("is-enemy-turn");
    setControlsLocked(false);
    setCaption(boardState.result ? "決着" : "味方ターン：次の1手を選択", boardState.result ? "result" : "ally");
    renderCapsules(boardState);
    if (boardState.result && submit) submit.disabled = true;
  }

  function skipReplay() {
    replayToken += 1;
    replaying = false;
    if (currentBoardState) {
      boardState = JSON.parse(JSON.stringify(currentBoardState));
      renderBoard(boardState);
    }
    board.classList.remove("is-enemy-turn");
    setControlsLocked(false);
    setCaption(boardState.result ? "決着" : "味方ターン：次の1手を選択", boardState.result ? "result" : "ally");
    setActionEnabled(false);
  }

  function markZoc() {
    (zocCells || []).forEach(function (point) {
      var cell = board.querySelector('[data-x="' + point.x + '"][data-y="' + point.y + '"]');
      if (cell) cell.classList.add("is-zoc");
    });
  }

  function isThreatCell(point) {
    return (threatCells || []).some(function (threat) { return sameCell(threat, point); });
  }

  function markThreats() {
    (threatCells || []).forEach(function (point) {
      var cell = board.querySelector('[data-x="' + point.x + '"][data-y="' + point.y + '"]');
      if (cell) cell.classList.add("is-threat");
    });
  }

  function highlightMoveGuide(moveType) {
    document.querySelectorAll(".mini-shogi-move-card").forEach(function (card) {
      card.classList.toggle("is-active", card.dataset.moveType === String(moveType || ""));
    });
  }

  function markForUnit(unitId) {
    clearMarks();
    selectedUnitId = unitId;
    selectedCapsulePiece = "";
    selectedActionMode = "move";
    selectedMove = null;
    actorInput.value = unitId;
    actionTypeInput.value = "";
    if (pieceTypeInput) pieceTypeInput.value = "";
    toXInput.value = "";
    toYInput.value = "";
    moveXInput.value = "";
    moveYInput.value = "";
    targetInput.value = "";
    if (submit) submit.disabled = true;
    var unit = unitById(unitId);
    var options = optionsByUnit[unitId] || {};
    if (selectedEl && unit) {
      selectedEl.textContent = isMiniAnimalShogi
        ? "選択中：" + unit.name + " / 動き：" + (unit.move_type_label || unit.move_type) + " / 敵マスで撃破"
        : (isMiniShogi ? "移動先または攻撃対象を選択: " + unit.name : unit.name + " / " + unit.move_type_label + " / " + unit.weapon_label);
    }
    highlightMoveGuide(unit && unit.move_type);
    if (hintEl) hintEl.textContent = "";
    if (replaying || boardState.result || !canAct) return;
    var unitEl = board.querySelector('[data-unit-id="' + unitId + '"]');
    if (unitEl) unitEl.classList.add("is-selected");
    board.querySelectorAll(".mini-tactics-cell").forEach(function (cell) {
      var point = {x: Number(cell.dataset.x), y: Number(cell.dataset.y)};
      if ((options.move_cells || []).some(function (move) { return sameCell(move, point); })) {
        cell.classList.add("is-move-option");
        if (isThreatCell(point)) cell.classList.add("is-danger-move");
      }
      if ((options.attackable_cells || []).some(function (attack) { return sameCell(attack, point); })) {
        cell.classList.add("is-attack-option");
      }
    });
    (options.targetable_unit_ids || []).forEach(function (targetId) {
      var target = unitById(targetId);
      if (!target) return;
      var targetCell = board.querySelector('[data-x="' + target.x + '"][data-y="' + target.y + '"]');
      if (targetCell) targetCell.classList.add("is-target-option");
    });
    markThreats();
  }

  function markForCapsule(pieceType) {
    clearMarks();
    selectedUnitId = "";
    selectedCapsulePiece = pieceType;
    selectedActionMode = "capsule";
    actorInput.value = "";
    actionTypeInput.value = "deploy_capsule";
    if (pieceTypeInput) pieceTypeInput.value = pieceType;
    var option = capsuleOptions[pieceType] || {};
    if (!option.count || !option.deploy_cells || !option.deploy_cells.length) {
      selectedCapsulePiece = "";
      selectedActionMode = "none";
      if (selectedEl) selectedEl.textContent = "選択中：なし";
      if (hintEl) hintEl.textContent = "このカプセルは今は再起動できません。";
      return;
    }
    if (selectedEl) selectedEl.textContent = (option.label || pieceType) + "を再起動：光ったマスに置けます";
    if (hintEl) hintEl.textContent = "光ったマスに置けます。";
    document.querySelectorAll('[data-capsule-piece="' + pieceType + '"]').forEach(function (button) {
      button.classList.add("is-selected");
    });
    (option.deploy_cells || []).forEach(function (point) {
      var cell = board.querySelector('[data-x="' + point.x + '"][data-y="' + point.y + '"]');
      if (cell) cell.classList.add("is-deploy-option");
    });
  }

  function markAfterMove(x, y) {
    var unit = unitById(selectedUnitId);
    if (!unit) return;
    selectedMove = {x: Number(x), y: Number(y)};
    moveXInput.value = String(x);
    moveYInput.value = String(y);
    toXInput.value = String(x);
    toYInput.value = String(y);
    targetInput.value = "";
    if (isMiniShogi) {
      postImmediateAction("move", {to_x: x, to_y: y});
      return;
    }
    if (submit) submit.disabled = false;
    board.querySelectorAll(".mini-tactics-cell").forEach(function (cell) {
      cell.classList.remove("is-selected-move", "is-target-option", "is-attack-option");
      if (Number(cell.dataset.x) === Number(x) && Number(cell.dataset.y) === Number(y)) {
        cell.classList.add("is-selected-move");
      }
    });
    var options = optionsByUnit[selectedUnitId] || {};
    var afterMove = (options.after_move || {})[String(x) + "," + String(y)] || {};
    if (hintEl) hintEl.textContent = afterMove.move_notice || "";
    (afterMove.attackable_cells || []).forEach(function (attack) {
      var attackCell = board.querySelector('[data-x="' + attack.x + '"][data-y="' + attack.y + '"]');
      if (attackCell) attackCell.classList.add("is-attack-option");
    });
    (afterMove.targetable_unit_ids || []).forEach(function (targetId) {
      var target = unitById(targetId);
      if (!target) return;
      var targetCell = board.querySelector('[data-x="' + target.x + '"][data-y="' + target.y + '"]');
      if (targetCell) targetCell.classList.add("is-target-option");
    });
  }

  board.addEventListener("click", function (event) {
    var unitEl = event.target.closest("[data-unit-id]");
    if (unitEl && unitEl.dataset.side === playableSide && !unitEl.classList.contains("is-core")) {
      if (replaying || boardState.result) return;
      if (!canAct) {
        if (hintEl) hintEl.textContent = turnMessage || "相手の手を待っています。";
        return;
      }
      markForUnit(unitEl.dataset.unitId);
      return;
    }
    var cell = event.target.closest(".mini-tactics-cell");
    if (!cell) return;
    if (selectedActionMode === "capsule" && selectedCapsulePiece) {
      if (!cell.classList.contains("is-deploy-option")) {
        if (hintEl) hintEl.textContent = "そこには再起動できません。";
        return;
      }
      postImmediateAction("deploy_capsule", {piece_type: selectedCapsulePiece, to_x: cell.dataset.x, to_y: cell.dataset.y});
      return;
    }
    if (!selectedUnitId) return;
    if (cell.classList.contains("is-move-option")) {
      markAfterMove(cell.dataset.x, cell.dataset.y);
      return;
    }
    if (unitEl && unitEl.dataset.side !== playableSide) {
      var enemyUnit = unitById(unitEl.dataset.unitId);
      var targetCell = unitEl.closest(".mini-tactics-cell");
      if (!targetCell || !targetCell.classList.contains("is-target-option")) {
        if (hintEl) hintEl.textContent = enemyUnit && enemyUnit.guarded ? "リーダーは護衛されているため狙えません。" : "攻撃できない対象です。";
        return;
      }
      targetInput.value = unitEl.dataset.unitId;
      if (isMiniShogi) {
        postImmediateAction("attack", {target_unit_id: unitEl.dataset.unitId});
      } else if (submit) {
        submit.disabled = false;
      }
    }
  });

  markZoc();
  markThreats();
  if (replayButton) replayButton.addEventListener("click", playSequence);
  if (skipReplayButton) skipReplayButton.addEventListener("click", skipReplay);
	  document.querySelectorAll("[data-capsule-piece]").forEach(function (button) {
	    button.addEventListener("click", function (event) {
	      event.preventDefault();
	      event.stopPropagation();
	      if (button.disabled || replaying || actionPending || boardState.result || !canAct) return;
	      selectedUnitId = "";
	      selectedCapsulePiece = "";
	      selectedActionMode = "capsule";
	      selectedMove = null;
	      actorInput.value = "";
	      actionTypeInput.value = "deploy_capsule";
	      targetInput.value = "";
	      markForCapsule(button.dataset.pieceType || button.dataset.capsulePiece);
	    });
	  });

  async function pollStateOnce() {
    if (!isOnlineBattle || !stateUrl || canAct || boardState.result || replaying || actionPending) return;
    try {
      var response = await fetch(stateUrl, {headers: {"Accept": "application/json"}});
      var data = await response.json().catch(function () { return null; });
      if (!response.ok || !data || !data.ok) throw new Error("通信確認中");
      if (data.updated_at && data.updated_at !== lastKnownUpdatedAt) {
        boardState = data.board_state || boardState;
        optionsByUnit = data.options_by_unit || {};
        capsuleOptions = data.capsule_options || {};
        zocCells = data.zoc_cells || [];
        threatCells = data.threat_cells || [];
        canAct = !!data.can_act;
        turnMessage = data.turn_message || "";
        lastKnownUpdatedAt = data.updated_at;
        renderBoard(boardState);
        renderCapsules(boardState);
        clearMarks();
      } else {
        canAct = !!data.can_act;
        turnMessage = data.turn_message || turnMessage;
      }
      setCaption(boardState.result ? "決着" : (turnMessage || "相手の手を待っています"), boardState.result ? "result" : (canAct ? "ally" : "enemy"));
      if (hintEl && !canAct && !boardState.result) hintEl.textContent = "相手の手を待っています。";
    } catch (error) {
      if (hintEl) hintEl.textContent = "通信確認中";
    }
  }

  function maybeStartPolling() {
    if (!isOnlineBattle || window.__miniShogiPollTimer) return;
    window.__miniShogiPollTimer = window.setInterval(pollStateOnce, 3000);
  }

  if (isMiniAnimalShogi) {
    setCaption(boardState.result ? "決着" : (turnMessage || "味方ターン：動かすミニロボを選択"), boardState.result ? "result" : (canAct ? "ally" : "enemy"));
    renderCapsules(boardState);
    var openingKey = "mini-shogi-opening:" + String(battleId || "");
    function closeOpening() {
      if (openingEl) openingEl.hidden = true;
      try { window.sessionStorage.setItem(openingKey, "1"); } catch (error) {}
    }
    var shouldShowOpening = !!openingEl && !!openingSequencePending;
    try {
      shouldShowOpening = shouldShowOpening && window.sessionStorage.getItem(openingKey) !== "1";
    } catch (error) {}
    if (shouldShowOpening) {
      openingEl.hidden = false;
      window.setTimeout(closeOpening, 1300);
      if (openingSkip) openingSkip.addEventListener("click", closeOpening);
    }
    maybeStartPolling();
  } else {
    playSequence();
  }
})();

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("battle-action-form");
  if (!form || form.dataset.bound === "1") return;
  form.dataset.bound = "1";

  const statusBox = document.getElementById("battle-status");
  const logBox = document.getElementById("battle-log");
  const messageBox = document.getElementById("battle-message");
  const attackUrl = form.dataset.attackUrl || "/battle/attack_async";

  const showMessage = (text) => {
    if (!messageBox) return;
    messageBox.textContent = text || "";
    if (text) {
      messageBox.classList.remove("is-hidden");
      window.clearTimeout(messageBox._clearTimer);
      messageBox._clearTimer = window.setTimeout(() => {
        messageBox.classList.add("is-hidden");
      }, 2400);
    } else {
      messageBox.classList.add("is-hidden");
    }
  };

  form.addEventListener("submit", async (event) => {
    const submitter = event.submitter;
    if (!submitter || submitter.value !== "attack") {
      return;
    }
    event.preventDefault();
    if (submitter.disabled) return;
    submitter.disabled = true;
    try {
      const body = new FormData();
      body.append("action", "attack");
      const response = await fetch(attackUrl, {
        method: "POST",
        body,
      });
      const data = await response.json();
      if (data.html_status && statusBox) {
        statusBox.innerHTML = data.html_status;
      }
      if (!data.ok) {
        showMessage(data.message || "処理に失敗しました。");
        return;
      }
      if (data.html_log && logBox) {
        logBox.insertAdjacentHTML("beforeend", data.html_log);
        logBox.scrollTop = logBox.scrollHeight;
      }
      showMessage(data.message || "");
    } catch (_e) {
      showMessage("通信エラーが発生しました。");
    } finally {
      submitter.disabled = false;
    }
  });
});

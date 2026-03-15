(() => {
  const pad2 = (n) => String(Math.max(0, n)).padStart(2, "0");

  const syncExploreCooldown = () => {
    const ctStatus = document.getElementById("home-ct-status");
    if (!ctStatus) {
      return;
    }
    const isAdmin = String(ctStatus.dataset.isAdmin || "0") === "1";
    const ctaButtons = Array.from(document.querySelectorAll("[data-explore-cta='1']"));
    if (isAdmin) {
      ctStatus.textContent = "CT状態: 管理者: 制限なし";
      ctaButtons.forEach((btn) => {
        btn.disabled = false;
      });
      return;
    }
    const readyAt = Number(ctStatus.dataset.ctReadyAt || "0");
    if (!Number.isFinite(readyAt) || readyAt <= 0) {
      ctStatus.textContent = "CT状態: 出撃可能";
      ctaButtons.forEach((btn) => {
        btn.disabled = false;
      });
      return;
    }

    let timerId = null;
    const tick = () => {
      const now = Math.floor(Date.now() / 1000);
      const remain = Math.max(0, readyAt - now);
      if (remain > 0) {
        const mm = Math.floor(remain / 60);
        const ss = remain % 60;
        ctStatus.textContent = `CT状態: クールタイム中 あと ${pad2(mm)}:${pad2(ss)}`;
        ctaButtons.forEach((btn) => {
          btn.disabled = true;
        });
      } else {
        ctStatus.textContent = "CT状態: 出撃可能";
        ctaButtons.forEach((btn) => {
          btn.disabled = false;
        });
        if (timerId !== null) {
          window.clearInterval(timerId);
        }
      }
    };

    tick();
    timerId = window.setInterval(tick, 1000);
  };

  const init = () => {
    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
      chatBox.scrollTop = chatBox.scrollHeight;
    }

    const exploreSelect = document.getElementById("explore-area-select");
    const mistHint = document.getElementById("mist-area-hint");
    const rushHint = document.getElementById("rush-area-hint");
    if (exploreSelect && mistHint && rushHint) {
      const syncAreaHints = () => {
        const isMist = exploreSelect.value === "layer_2_mist";
        const isRush = exploreSelect.value === "layer_2_rush";
        mistHint.classList.toggle("is-hidden", !isMist);
        rushHint.classList.toggle("is-hidden", !isRush);
      };
      exploreSelect.addEventListener("change", syncAreaHints);
      syncAreaHints();
    }

    const inviteCopyBtn = document.getElementById("invite-copy-btn");
    if (inviteCopyBtn) {
      inviteCopyBtn.addEventListener("click", async () => {
        const targetId = inviteCopyBtn.getAttribute("data-copy-target");
        const input = targetId ? document.getElementById(targetId) : null;
        if (!input) {
          return;
        }
        const text = String(input.value || "");
        if (!text) {
          return;
        }
        try {
          await navigator.clipboard.writeText(text);
          inviteCopyBtn.textContent = "コピー済み";
          setTimeout(() => {
            inviteCopyBtn.textContent = "コピー";
          }, 1200);
        } catch (_) {
          input.focus();
          input.select();
        }
      });
    }

    syncExploreCooldown();
  };

  document.addEventListener("DOMContentLoaded", init);
})();

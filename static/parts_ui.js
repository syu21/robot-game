(() => {
  const forms = Array.from(document.querySelectorAll("form[data-submit-lock='1']"));
  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.submitLocked === "1") {
        event.preventDefault();
        return;
      }
      const submitter =
        (event.submitter && event.submitter.tagName ? event.submitter : null) ||
        form.querySelector("button[type='submit'], input[type='submit']");
      if (!submitter) return;
      form.dataset.submitLocked = "1";
      submitter.dataset.originalText = submitter.textContent || submitter.value || "";
      const loadingText = form.dataset.loadingText || "送信中...";
      if ("textContent" in submitter && submitter.textContent) {
        submitter.textContent = loadingText;
      } else if ("value" in submitter) {
        submitter.value = loadingText;
      }
      submitter.disabled = true;
      form.classList.add("is-submitting");
    });
  });

  const links = Array.from(document.querySelectorAll("[data-busy-link='1']"));
  links.forEach((link) => {
    link.addEventListener("click", () => {
      link.classList.add("is-pending");
    });
  });
})();

(() => {
  const root = document.documentElement;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const spot = document.querySelector(".spot");
  const dialog = document.getElementById("lightbox");
  const dialogImg = dialog?.querySelector("img");
  const dialogCap = dialog?.querySelector(".lightbox-cap");

  if (spot && !reduce) {
    window.addEventListener(
      "pointermove",
      (event) => {
        root.style.setProperty("--mx", `${event.clientX}px`);
        root.style.setProperty("--my", `${event.clientY}px`);
      },
      { passive: true },
    );
  }

  const heroPhoto = document.querySelector(".hero-photo");
  if (heroPhoto && !reduce) {
    window.addEventListener(
      "scroll",
      () => {
        const y = Math.min(window.scrollY, 600);
        heroPhoto.style.transform = `scale(${1.06 + y / 8000}) translate3d(0, ${y * 0.12}px, 0)`;
      },
      { passive: true },
    );
  }

  document.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!dialog || !dialogImg || !dialogCap) return;
      dialogImg.src = button.getAttribute("data-open") || "";
      dialogImg.alt = button.getAttribute("data-label") || "";
      dialogCap.textContent = button.getAttribute("data-label") || "";
      if (typeof dialog.showModal === "function") dialog.showModal();
    });
  });

  dialog?.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
  dialog?.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
})();

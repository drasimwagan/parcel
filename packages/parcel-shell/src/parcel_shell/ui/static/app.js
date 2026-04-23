// Parcel admin UI — small client-side glue.

(function () {
  const VALID = ["plain", "blue", "dark"];

  function setTheme(name) {
    if (!VALID.includes(name)) name = "plain";
    document.documentElement.dataset.theme = name;
    try {
      localStorage.setItem("parcel_theme", name);
    } catch (e) {
      /* ignore */
    }
  }

  window.setTheme = setTheme;
  window.parcelTheme = function () {
    try {
      return localStorage.getItem("parcel_theme") || "plain";
    } catch (e) {
      return "plain";
    }
  };
})();

// HTMX flash: servers can push a flash after a non-redirect HTMX action
document.addEventListener("DOMContentLoaded", function () {
  document.body.addEventListener("flash", function (evt) {
    const { kind, msg } = evt.detail || {};
    if (!msg) return;
    const container = document.getElementById("toast-region");
    if (!container) return;
    const div = document.createElement("div");
    div.className = "alert " + (kind || "info");
    div.textContent = msg;
    container.appendChild(div);
    setTimeout(() => div.remove(), 4000);
  });
});

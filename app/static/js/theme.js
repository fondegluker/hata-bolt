(function () {
  const KEY = "hata-theme";
  function apply(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(KEY, t); } catch (e) {}
  }
  function current() {
    return document.documentElement.getAttribute("data-theme") || "dark";
  }
  function toggle() {
    apply(current() === "dark" ? "light" : "dark");
  }
  const btn = document.getElementById("themeToggle");
  if (btn) btn.addEventListener("click", toggle);
})();

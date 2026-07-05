(function () {
  const cfg = window.HATA_CONFIG || {};
  function setFromCfg() {
    document.querySelectorAll("[data-cfg]").forEach(node => {
      const path = node.getAttribute("data-cfg");
      const val = getPath(cfg, path);
      if (node.type === "checkbox") node.checked = !!val;
      else node.value = val != null ? val : "";
    });
  }
  function getPath(o, p) {
    return p.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
  }
  function setPath(o, p, v) {
    const parts = p.split(".");
    let n = o;
    for (let i = 0; i < parts.length - 1; i++) { if (!(parts[i] in n)) n[parts[i]] = {}; n = n[parts[i]]; }
    n[parts[parts.length - 1]] = v;
  }
  function collect() {
    const out = {};
    document.querySelectorAll("[data-cfg]").forEach(node => {
      const path = node.getAttribute("data-cfg");
      const v = node.type === "checkbox" ? node.checked :
                node.type === "number" ? (node.value === "" ? 0 : Number(node.value)) :
                node.value;
      setPath(out, path, v);
    });
    return out;
  }
  function flash(kind, msg) {
    const f = document.getElementById("flash");
    f.innerHTML = '<div class="flash ' + kind + '">' + msg + "</div>";
    setTimeout(() => (f.innerHTML = ""), 3500);
  }
  document.addEventListener("DOMContentLoaded", () => {
    setFromCfg();
    document.getElementById("btn-save").addEventListener("click", () => {
      const updates = collect();
      fetch("/api/settings", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates })
      }).then(r => r.json()).then(() => flash("ok", "Настройки сохранены. Перезагрузите страницу для применения изменений БД/карты."))
        .catch(() => flash("err", "Ошибка сохранения."));
    });
  });
})();

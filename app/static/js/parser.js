(function () {
  let pollTimer = null, logSince = 0, currentRunId = null;

  const el = id => document.getElementById(id);

  function setRunning(on) {
    el("btn-start").disabled = on;
    el("btn-stop").disabled = !on;
  }

  function start() {
    const body = {
      source: el("run-source").value,
      profile: el("run-profile").value,
      dry_run: el("run-dry").checked
    };
    el("logView").innerHTML = "";
    logSince = 0;
    fetch("/api/parse/start", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    }).then(r => r.json()).then(d => {
      currentRunId = d.run_id;
      setRunning(true);
      poll();
    });
  }

  function stop() {
    fetch("/api/parse/stop", { method: "POST" });
  }

  function poll() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      fetch("/api/parse/active").then(r => r.json()).then(s => {
        el("phase").textContent = s.phase || "—";
        el("processed").textContent = s.processed;
        el("total").textContent = s.total;
        el("bar").style.width = (s.progress || 0) + "%";
        el("s-new").textContent = s.new;
        el("s-upd").textContent = s.updated;
        el("s-photo").textContent = s.photos;
        el("s-err").textContent = s.errors;
        if (!s.active) { setRunning(false); clearInterval(pollTimer); pollTimer = null; }
      });
      if (currentRunId) {
        fetch("/api/parse/logs?run_id=" + currentRunId + "&since=" + logSince).then(r => r.json()).then(rows => {
          const view = el("logView");
          rows.forEach(r => {
            logSince = Math.max(logSince, r.id);
            const line = document.createElement("div");
            line.className = "log-line";
            line.innerHTML = '<span class="ts">' + (r.ts || "").substr(11, 8) + '</span> ' +
              '<span class="lvl-' + r.level + '">' + r.level + '</span> ' +
              '<span class="src">[' + r.source + ']</span> ' + r.message;
            view.appendChild(line);
            view.scrollTop = view.scrollHeight;
          });
        });
      }
    }, 1200);
  }

  document.addEventListener("DOMContentLoaded", () => {
    el("btn-start").addEventListener("click", start);
    el("btn-stop").addEventListener("click", stop);
    fetch("/api/parse/active").then(r => r.json()).then(s => {
      if (s.active) { currentRunId = s.run_id; setRunning(true); poll(); }
    });
  });
})();

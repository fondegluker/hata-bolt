(function () {
  const cfg = window.HATA_MAP || {};
  let map, cluster, allFeatures = [], drawerEl, lbEl, lbImgs = [], lbIdx = 0;

  function pin(color) {
    return L.divIcon({
      className: "hata-pin",
      html: '<span style="display:block;width:14px;height:14px;border-radius:50%;background:' + color +
            ';border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.5)"></span>',
      iconSize: [18, 18], iconAnchor: [9, 9], popupAnchor: [0, -10]
    });
  }

  function load() {
    const types = [];
    if (document.getElementById("f-abandoned").checked) types.push("abandoned");
    if (document.getElementById("f-commercial").checked) types.push("commercial");
    const region = document.getElementById("f-region").value;
    const sale = document.getElementById("f-sale").value;
    const qs = new URLSearchParams();
    const promises = types.map(t => fetch("/api/houses?object_type=" + t +
      (region ? "&region=" + encodeURIComponent(region) : "") +
      (sale ? "&sale_method=" + sale : "")).then(r => r.json()));
    Promise.all(promises).then(arrs => {
      allFeatures = [].concat.apply([], arrs);
      render();
    });
  }

  function render() {
    if (cluster) map.removeLayer(cluster);
    cluster = L.markerClusterGroup({ maxClusterRadius: cfg.max_cluster_radius || 50 });
    allFeatures.forEach(h => {
      if (h.latitude == null || h.longitude == null) return;
      const m = L.marker([h.latitude, h.longitude], { icon: pin(h.marker_color) });
      const thumb = h.thumb_url ? '<img src="' + h.thumb_url + '">' : '';
      m.bindPopup(
        '<div class="popup-card">' + thumb +
        '<p class="pt">' + (h.title || "Объект") + '</p>' +
        '<p class="pa">' + [h.locality, h.address].filter(Boolean).join(", ") + '</p>' +
        (h.price != null ? '<p class="pp">' + Number(h.price).toLocaleString("ru-RU") + ' BYN</p>' : '') +
        '<a href="#" onclick="HataMap.openDetail(' + h.id + ');return false" style="display:inline-block;margin-top:6px">Подробнее →</a>' +
        '</div>'
      );
      m.on("click", () => openDetail(h.id));
      cluster.addLayer(m);
    });
    map.addLayer(cluster);
  }

  function openDetail(id) {
    fetch("/api/house/" + id).then(r => r.json()).then(h => {
      const body = drawerEl.querySelector(".drawer-body");
      const kv = (k, v) => v ? '<div class="k">' + k + '</div><div class="v">' + v + '</div>' : "";
      let photosHtml = "";
      lbImgs = (h.photos || []).map(p => p.local_path ? "/photos/" + p.local_path : p.url);
      (h.photos || []).forEach(p => {
        const src = p.local_path ? "/photos/" + p.local_path : p.url;
        photosHtml += '<img src="' + src + '" data-i="' + (lbImgs.indexOf(src)) + '" onclick="HataMap.openLightbox(' + lbImgs.indexOf(src) + ')">';
      });
      body.innerHTML =
        '<div class="kv">' +
        kv("Тип", h.object_type === "abandoned" ? "Пустующий дом" : "Коммерческая") +
        kv("Регион", h.region) + kv("Район", h.district) + kv("Сельсовет", h.council) +
        kv("Населённый пункт", h.locality) + kv("Адрес", h.address) +
        kv("Цена", h.price != null ? Number(h.price).toLocaleString("ru-RU") + " BYN" : null) +
        kv("Продажа", h.sale_method === "auction" ? "Аукцион" : "Напрямую") +
        kv("Площадь", h.area_total != null ? h.area_total + " м²" : null) +
        kv("Участок", h.area_land != null ? h.area_land + " сот" : null) +
        kv("Комнат", h.rooms) + kv("Этажей", h.floors) +
        kv("Статус", h.status) + kv("Источник", '<a href="' + h.source_url + '" target="_blank">открыть ↗</a>') +
        '</div>' +
        (h.description ? '<p style="margin-top:14px;color:var(--text-dim);font-size:13px">' + h.description + '</p>' : '') +
        (photosHtml ? '<div class="section-title" style="margin-top:16px">Фотографии (' + lbImgs.length + ')</div><div class="gallery">' + photosHtml + '</div>' : '');
      drawerEl.classList.add("open");
      document.querySelector(".drawer-backdrop").classList.add("open");
    });
  }

  function closeDrawer() {
    drawerEl.classList.remove("open");
    document.querySelector(".drawer-backdrop").classList.remove("open");
  }

  function openLightbox(i) {
    lbIdx = i; renderLb(); lbEl.classList.add("open");
  }
  function renderLb() {
    lbEl.querySelector("img").src = lbImgs[lbIdx] || "";
    lbEl.querySelector(".lb-counter").textContent = (lbIdx + 1) + " / " + lbImgs.length;
  }
  function lbNav(d) {
    lbIdx = (lbIdx + d + lbImgs.length) % lbImgs.length; renderLb();
  }

  function init() {
    map = L.map("map", { center: [cfg.default_lat || 53.9, cfg.default_lng || 27.56], zoom: cfg.default_zoom || 7 });
    L.tileLayer(cfg.tile_url || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: cfg.tile_attribution || "&copy; OpenStreetMap", maxZoom: 19
    }).addTo(map);

    drawerEl = document.createElement("div");
    drawerEl.className = "drawer";
    drawerEl.innerHTML =
      '<div class="drawer-head"><h3>Объект</h3><button class="drawer-close">×</button></div>' +
      '<div class="drawer-body"></div>';
    document.body.appendChild(drawerEl);
    const back = document.createElement("div");
    back.className = "drawer-backdrop";
    document.body.appendChild(back);
    back.addEventListener("click", closeDrawer);
    drawerEl.querySelector(".drawer-close").addEventListener("click", closeDrawer);

    lbEl = document.createElement("div");
    lbEl.className = "lightbox";
    lbEl.innerHTML =
      '<button class="lb-close">×</button><button class="lb-nav lb-prev">‹</button>' +
      '<img src=""><button class="lb-nav lb-next">›</button><div class="lb-counter"></div>';
    document.body.appendChild(lbEl);
    lbEl.querySelector(".lb-close").addEventListener("click", () => lbEl.classList.remove("open"));
    lbEl.querySelector(".lb-prev").addEventListener("click", () => lbNav(-1));
    lbEl.querySelector(".lb-next").addEventListener("click", () => lbNav(1));
    document.addEventListener("keydown", e => {
      if (!lbEl.classList.contains("open")) return;
      if (e.key === "Escape") lbEl.classList.remove("open");
      if (e.key === "ArrowLeft") lbNav(-1);
      if (e.key === "ArrowRight") lbNav(1);
    });

    ["f-abandoned", "f-commercial", "f-region", "f-sale"].forEach(id =>
      document.getElementById(id).addEventListener("change", load));
    load();
  }

  window.HataMap = { openDetail, openLightbox };
  document.addEventListener("DOMContentLoaded", init);
})();

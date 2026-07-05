import datetime as dt
import json
import os
import random
import time

from app import config, db

REGIONS = [
    ("Брестская область", "Брестский район", "Чернинский сельсовет", "д. Черняки"),
    ("Витебская область", "Полоцкий район", "Ветринский сельсовет", "д. Ветрино"),
    ("Гомельская область", "Гомельский район", "Поколюбичский сельсовет", "д. Поколюбичи"),
    ("Гродненская область", "Щучинский район", "Остринский сельсовет", "д. Острино"),
    ("Минская область", "Минский район", "Боровлянский сельсовет", "д. Боровляны"),
    ("Минская область", "Слуцкий район", "Соражский сельсовет", "д. Сорочи"),
    ("Минская область", "Солигорский район", "Горбовичский сельсовет", "д. Горбовичи"),
    ("Могилёвская область", "Могилёвский район", "Кадинский сельсовет", "д. Кадино"),
    ("Могилёвская область", "Кричевский район", "Костюковичский сельсовет", "д. Костюковичи"),
    ("Брестская область", "Кобринский район", "Городецкий сельсовет", "д. Городец"),
]
STREETS = ["ул. Лесная", "ул. Садовая", "ул. Центральная", "ул. Полевая", "ул. Школьная", "ул. Мира", "пер. Новый"]
TITLES = [
    "Жилой дом", "Пустующий жилой дом", "Деревянный дом", "Кирпичный дом",
    "Дом с участком", "Жилой дом бревенчатый", "Дом с хозяйственными постройками",
]
DESC = [
    "Деревянный жилой дом, требует ремонта. Подводки электричества и воды имеются. Рядом лес, река.",
    "Кирпичный дом, частичные коммуникации. Участок ровный, сухой. Тихое место.",
    "Бревенчатый дом 1960-х годов. Крыша требует замены. Возможна продажа с рассрочкой до 3 лет.",
    "Пустующий дом на окраине деревни. Подходит для дачного использования. Рядом озеро.",
    "Жилой фонд, признан пустующим. Земельный участок оформлен. Коммуникации частично.",
]


def _mock_objects(object_type, count, base_url):
    rng = random.Random(hash(object_type) & 0xFFFFFFFF)
    out = []
    for i in range(count):
        region, district, council, locality = rng.choice(REGIONS)
        lat = 51.3 + rng.random() * 4.0
        lng = 23.2 + rng.random() * 6.0
        price = rng.choice([1, 3, 5, 8, 12, 15, 20, 25, 30, 40]) * 100
        sale = rng.choice(["auction", "direct"]) if object_type == "abandoned" else "auction"
        area = round(40 + rng.random() * 160, 1)
        land = round(10 + rng.random() * 25, 2)
        rooms = rng.randint(2, 5)
        floors = rng.randint(1, 2)
        sid = f"{object_type}-mock-{i+1:04d}"
        title = rng.choice(TITLES)
        addr = f"{locality}, {rng.choice(STREETS)}, {rng.randint(1, 40)}"
        n_photos = rng.randint(1, 5)
        photos = []
        for p in range(n_photos):
            w = rng.choice([800, 1024, 1200])
            h = rng.choice([600, 768, 900])
            photos.append(
                {
                    "url": f"{base_url}/img/mock/{object_type}-{i+1:04d}-{p+1}.jpg",
                    "width": w,
                    "height": h,
                    "ordr": p,
                }
            )
        out.append(
            {
                "object_type": object_type,
                "source_id": sid,
                "source_url": f"{base_url}/object/{sid}",
                "title": title,
                "region": region,
                "district": district,
                "council": council,
                "locality": locality,
                "address": addr,
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "price": price,
                "price_note": "BYN" if sale == "direct" else "начальная цена, BYN",
                "sale_method": sale,
                "area_total": area,
                "area_land": land,
                "rooms": rooms,
                "floors": floors,
                "description": rng.choice(DESC),
                "status": "active",
                "photos": photos,
            }
        )
    return out


class Engine:
    def __init__(self, profile, source_filter, dry_run, logger, state):
        self.profile_name = profile
        self.profile = config.get(f"parser.profiles.{profile}", config.get("parser.profiles.balanced"))
        self.source_filter = source_filter
        self.dry_run = dry_run
        self.log = logger
        self.state = state
        self.sources_cfg = config.get("parser.sources", {})
        self.proxy = config.get("parser.proxy", {})
        self.uas = config.get("parser.user_agents", [])
        self.download_photos = config.get("parser.download_photos", True)
        self.photo_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", config.get("parser.photo_dir", "data/photos"))
        )
        self.max_objects = config.get("parser.max_objects_per_run", 0) or 0
        self._hour_window = []
        self._ua_idx = 0

    def _wanted_sources(self):
        items = []
        for key, src in self.sources_cfg.items():
            if not src.get("enabled", True):
                continue
            if self.source_filter and self.source_filter != "all" and self.source_filter != key:
                continue
            items.append((key, src))
        return items

    def _ua(self):
        if not self.uas:
            return None
        ua = self.uas[self._ua_idx % len(self.uas)]
        self._ua_idx += 1
        return ua

    def _throttle(self):
        delay = random.uniform(self.profile["delay_min_seconds"], self.profile["delay_max_seconds"])
        time.sleep(delay)

    def _hour_cap_wait(self):
        limit = self.profile.get("per_hour_limit", 400)
        now = time.time()
        self._hour_window = [t for t in self._hour_window if now - t < 3600]
        if len(self._hour_window) >= limit:
            wait = 3600 - (now - self._hour_window[0])
            self.log.warn(f"Часовой лимит {limit} достигнут, пауза {int(wait)}с")
            time.sleep(max(wait, 1))
        self._hour_window.append(time.time())

    def _batch_pace(self, count):
        if count and count % self.profile["batch_size"] == 0:
            self.log.info(f"Пауза между пакетами {self.profile['batch_pause_seconds']}с (обработано {count})")
            time.sleep(self.profile["batch_pause_seconds"])

    def run(self):
        sources = self._wanted_sources()
        if not sources:
            self.log.warn("Нет активных источников для парсинга")
            return
        self.log.info(
            f"Старт. профиль={self.profile_name} sources={[k for k,_ in sources]} dry_run={self.dry_run} "
            f"proxy={'on' if self.proxy.get('enabled') else 'off'}"
        )
        all_items = []
        for key, src in sources:
            if self.state["stop"]:
                break
            items = self._collect_source(key, src)
            all_items.extend(items)
        if self.max_objects and len(all_items) > self.max_objects:
            all_items = all_items[: self.max_objects]
        self.state["total"] = len(all_items)
        self.state["phase"] = "processing"
        self.log.info(f"Найдено объектов: {len(all_items)}. Начинаю обработку и загрузку фото.")
        for idx, item in enumerate(all_items, 1):
            if self.state["stop"]:
                self.log.info("Остановлено пользователем")
                break
            self._hour_cap_wait()
            self._throttle()
            self._process_item(item)
            self.state["processed"] = idx
            self.state["progress"] = int(idx / max(len(all_items), 1) * 100)
            self._batch_pace(idx)
        self.state["phase"] = "done"

    def _collect_source(self, key, src):
        self.log.info(f"Сбор списка: {src.get('label')} ({src.get('base_url')})", source=key)
        if self.dry_run:
            count = random.randint(18, 30)
            items = _mock_objects(src.get("object_type", key), count, src.get("base_url"))
            self.log.info(f"[mock] сгенерировано {len(items)} объектов", source=key)
            return items
        try:
            return self._scrape_list(key, src)
        except Exception as e:  # noqa: BLE001
            self.state["errors"] += 1
            self.log.error(f"Сбор списка не удался: {e}", source=key)
            return []

    def _scrape_list(self, key, src):
        from playwright.sync_api import sync_playwright

        base = src["base_url"]
        list_path = src.get("list_path", "/")
        items = []
        with sync_playwright() as p:
            browser = self._launch(p)
            page = browser.new_page(user_agent=self._ua())
            try:
                url = base.rstrip("/") + list_path
                self.log.info(f"GET {url}", source=key)
                resp = page.goto(url, timeout=self.profile["request_timeout_seconds"] * 1000, wait_until="domcontentloaded")
                if resp and resp.status >= 400:
                    self.log.warn(f"HTTP {resp.status} на {url}", source=key)
                    return items
                # The abandoned registry renders object cards server-side; collect links to detail pages.
                anchors = page.eval_on_selector_all(
                    "a[href*='abandonedObject'], a[href*='object'], a[href*='/lot/']",
                    "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim()}))",
                )
                seen = set()
                for a in anchors:
                    href = a.get("href")
                    if not href or href in seen:
                        continue
                    if base not in href:
                        continue
                    seen.add(href)
                    items.append({"_list_url": href, "object_type": src.get("object_type", key)})
                self.log.info(f"Найдено ссылок на объекты: {len(items)}", source=key)
            finally:
                browser.close()
        return items

    def _launch(self, p):
        kwargs = {"headless": True}
        proxy_cfg = self.proxy
        if proxy_cfg.get("enabled") and proxy_cfg.get("server"):
            kwargs["proxy"] = {
                "server": proxy_cfg["server"],
                "username": proxy_cfg.get("username") or None,
                "password": proxy_cfg.get("password") or None,
            }
        return p.chromium.launch(**kwargs)

    def _process_item(self, item):
        if "_list_url" in item:
            detail = self._scrape_detail(item["_list_url"], item["object_type"])
            if not detail:
                self.state["errors"] += 1
                return
            item = {**detail, "object_type": item["object_type"]}
        self._upsert_house(item)

    def _scrape_detail(self, url, object_type):
        from playwright.sync_api import sync_playwright

        for attempt in range(self.profile.get("retry_attempts", 2)):
            try:
                with sync_playwright() as p:
                    browser = self._launch(p)
                    page = browser.new_page(user_agent=self._ua())
                    try:
                        resp = page.goto(url, timeout=self.profile["request_timeout_seconds"] * 1000, wait_until="domcontentloaded")
                        if resp and resp.status in (403, 429):
                            self.log.warn(f"HTTP {resp.status} блокировка на {url}, backoff")
                            time.sleep(self.profile["backoff_base_seconds"] * (attempt + 2))
                            continue
                        if resp and resp.status >= 500:
                            time.sleep(self.profile["backoff_base_seconds"])
                            continue
                        html = page.content()
                        return self._parse_detail_html(url, html, object_type)
                    finally:
                        browser.close()
            except Exception as e:  # noqa: BLE001
                self.log.warn(f"detail error {url}: {e}; попытка {attempt+1}")
                time.sleep(self.profile["backoff_base_seconds"])
        return None

    def _parse_detail_html(self, url, html, object_type):
        """Best-effort extraction from a detail page. The markup of eri2/au varies,
        so we pull labelled key/value rows generically and read photo <img> tags."""
        import re
        from html.parser import HTMLParser

        class _TableParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.pairs = {}
                self._key = None
                self._val_buf = []
                self._in_td = False
                self._imgs = []

            def handle_starttag(self, tag, attrs):
                if tag == "td":
                    self._in_td = True
                    self._val_buf = []
                elif tag == "img":
                    d = dict(attrs)
                    src = d.get("src") or d.get("data-src")
                    if src and ("photo" in src.lower() or "img" in src.lower() or "/upload" in src.lower()):
                        self._imgs.append(src)

            def handle_endtag(self, tag):
                if tag == "td" and self._in_td:
                    self._in_td = False
                    txt = " ".join("".join(self._val_buf).split())
                    if txt:
                        if self._key is None:
                            self._key = txt
                        else:
                            self.pairs[self._key] = txt
                            self._key = None

            def handle_data(self, data):
                if self._in_td:
                    self._val_buf.append(data)

        parser = _TableParser()
        parser.feed(html)
        pairs = parser.pairs
        def pick(*keys):
            for k in keys:
                for pk, pv in pairs.items():
                    if k.lower() in pk.lower():
                        return pv
            return None

        title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        title = title.group(1).strip() if title else None
        photos = []
        base = url.split("/")[2] if "://" in url else ""
        proto = "https:" if not url.startswith("http") else url.split("://")[0] + ":"
        for src in parser._imgs:
            if src.startswith("//"):
                src = proto + src
            elif src.startswith("/"):
                src = f"https://{base}{src}"
            photos.append({"url": src, "ordr": len(photos)})
        return {
            "source_id": url.rstrip("/").split("/")[-1],
            "source_url": url,
            "title": title,
            "region": pick("область", "регион"),
            "district": pick("район"),
            "council": pick("сельсовет", "совет"),
            "locality": pick("населен", "населён", "деревня", "город", "агрогородок"),
            "address": pick("адрес"),
            "latitude": _fnum(pick("широта", "lat", "координата")),
            "longitude": _fnum(pick("долгота", "lng", "lon")),
            "price": _fnum(pick("цена", "стоимость", "начальн")),
            "price_note": pick("цена", "стоимость"),
            "sale_method": "auction" if ("аукцион" in (pick("способ", "продажа") or "").lower() or "auction" in url) else "direct",
            "area_total": _fnum(pick("площадь жил", "площадь общ", "площадь")),
            "area_land": _fnum(pick("площадь зем", "площадь участ")),
            "rooms": _int(pick("комнат", "комнаты")),
            "floors": _int(pick("этаж", "этажность")),
            "description": pick("описание", "характерист", "сведения"),
            "photos": photos,
        }

    def _upsert_house(self, item):
        c = db.conn()
        try:
            with c.cursor() as cur:
                cur.execute(
                    """INSERT INTO houses
                       (object_type, source_id, source_url, title, region, district, council,
                        locality, address, latitude, longitude, price, price_note, sale_method,
                        area_total, area_land, rooms, floors, description, status, last_seen)
                       VALUES (%(object_type)s,%(source_id)s,%(source_url)s,%(title)s,%(region)s,
                               %(district)s,%(council)s,%(locality)s,%(address)s,%(latitude)s,%(longitude)s,
                               %(price)s,%(price_note)s,%(sale_method)s,%(area_total)s,%(area_land)s,
                               %(rooms)s,%(floors)s,%(description)s,%(status)s, now())
                       ON CONFLICT (object_type, source_id) DO UPDATE SET
                         title=EXCLUDED.title, region=EXCLUDED.region, district=EXCLUDED.district,
                         council=EXCLUDED.council, locality=EXCLUDED.locality, address=EXCLUDED.address,
                         latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, price=EXCLUDED.price,
                         price_note=EXCLUDED.price_note, sale_method=EXCLUDED.sale_method,
                         area_total=EXCLUDED.area_total, area_land=EXCLUDED.area_land,
                         rooms=EXCLUDED.rooms, floors=EXCLUDED.floors, description=EXCLUDED.description,
                         status=EXCLUDED.status, last_seen=now(), updated_at=now()
                       RETURNING (xmax = 0) AS inserted, id""",
                    {
                        "object_type": item.get("object_type"),
                        "source_id": item.get("source_id"),
                        "source_url": item.get("source_url"),
                        "title": item.get("title"),
                        "region": item.get("region"),
                        "district": item.get("district"),
                        "council": item.get("council"),
                        "locality": item.get("locality"),
                        "address": item.get("address"),
                        "latitude": item.get("latitude"),
                        "longitude": item.get("longitude"),
                        "price": item.get("price"),
                        "price_note": item.get("price_note"),
                        "sale_method": item.get("sale_method"),
                        "area_total": item.get("area_total"),
                        "area_land": item.get("area_land"),
                        "rooms": item.get("rooms"),
                        "floors": item.get("floors"),
                        "description": item.get("description"),
                        "status": item.get("status", "active"),
                    },
                )
                row = cur.fetchone()
                inserted = row[0]
                house_id = row[1]
            c.commit()
        finally:
            db.release(c)
        if inserted:
            self.state["new"] += 1
            self.log.info(f"Новый объект: {item.get('title')} ({item.get('source_id')})")
        else:
            self.state["updated"] += 1
        if self.download_photos and item.get("photos"):
            self._download_photos(house_id, item["photos"])

    def _download_photos(self, house_id, photos):
        os.makedirs(self.photo_dir, exist_ok=True)
        n = 0
        for ph in photos:
            if self.state["stop"]:
                break
            url = ph.get("url")
            if not url:
                continue
            ext = ".jpg"
            if "." in url.split("/")[-1]:
                e = url.split("/")[-1].rsplit(".", 1)[-1].split("?")[0]
                if e.lower() in ("jpg", "jpeg", "png", "webp", "gif"):
                    ext = "." + e.lower()
            local = f"{house_id}_{ph.get('ordr', 0)}{ext}"
            full = os.path.join(self.photo_dir, local)
            ok = False
            try:
                if url.endswith("/img/mock/" + url.split("/img/mock/")[-1]):
                    # mock placeholder image (svg)
                    self._write_placeholder(full, ph.get("width", 800), ph.get("height", 600),
                                            ph.get("ordr", 0))
                    ok = True
                else:
                    self._fetch_photo(url, full)
                    ok = True
                n += 1
            except Exception as e:  # noqa: BLE001
                self.log.warn(f"Фото не загружено {url}: {e}", source="photos")
            self._save_photo_row(house_id, url, local if ok else None, ok, ph.get("ordr", 0),
                                 ph.get("width"), ph.get("height"))
        if n:
            self.state["photos"] += n
            self.log.info(f"Загружено фото: {n} для объекта #{house_id}", source="photos")

    def _save_photo_row(self, house_id, url, local, ok, ordr, w, h):
        c = db.conn()
        try:
            with c.cursor() as cur:
                cur.execute(
                    """INSERT INTO photos (house_id, url, local_path, downloaded, ordr, width, height)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (house_id, url, local, ok, ordr, w, h),
                )
            c.commit()
        finally:
            db.release(c)

    def _fetch_photo(self, url, dest):
        # Use Playwright to fetch images so the request shares the browser's TLS fingerprint.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = self._launch(p)
            page = browser.new_page(user_agent=self._ua())
            try:
                resp = page.goto(url, timeout=self.profile["request_timeout_seconds"] * 1000)
                if resp and resp.status < 400:
                    body = resp.body()
                    with open(dest, "wb") as f:
                        f.write(body)
                else:
                    raise RuntimeError(f"photo HTTP {resp.status if resp else 'no-response'}")
            finally:
                browser.close()

    def _write_placeholder(self, dest, w, h, idx):
        # Generate a real image locally for mock mode so the lightbox has something to show.
        from PIL import Image, ImageDraw

        palette = [(37, 99, 235), (234, 88, 12), (22, 163, 74), (148, 163, 184)]
        base = palette[idx % len(palette)]
        img = Image.new("RGB", (w, h), base)
        d = ImageDraw.Draw(img)
        for y in range(0, h, 40):
            shade = tuple(max(0, c - 20) for c in base)
            d.rectangle([0, y, w, y + 18], fill=shade)
        try:
            d.text((20, 20), "Hata mock", fill=(255, 255, 255))
        except Exception:
            pass
        img.save(dest, "JPEG", quality=70)


def _fnum(v):
    if v is None:
        return None
    import re

    m = re.search(r"[-+]?\d[\d\s.,]*", str(v).replace("\xa0", " "))
    if not m:
        return None
    num = m.group(0).replace(" ", "").replace("\xa0", "").replace(".", ",").split(",")[0]
    num = num.replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def _int(v):
    if v is None:
        return None
    import re

    m = re.search(r"\d+", str(v))
    return int(m.group(0)) if m else None

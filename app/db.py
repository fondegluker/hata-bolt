import psycopg2
import psycopg2.extras
import threading

from app import config

_pool = []
_lock = threading.Lock()


def _dsn():
    db = config.get("db")
    return {
        "host": db.get("host", "localhost"),
        "port": db.get("port", 5432),
        "dbname": db.get("name", "hata"),
        "user": db.get("user", "hata"),
        "password": db.get("password", "hata"),
    }


def _connect():
    return psycopg2.connect(**_dsn())


def conn():
    """Borrow a raw connection from a tiny thread-safe pool."""
    with _lock:
        if _pool:
            return _pool.pop()
    return _connect()


def release(c):
    try:
        c.rollback()
    except Exception:
        try:
            c.close()
        except Exception:
            pass
        return
    with _lock:
        if len(_pool) < 4:
            _pool.append(c)
        else:
            c.close()


def query(sql, params=None, fetch="all"):
    c = conn()
    try:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            if fetch == "all":
                rows = cur.fetchall()
                return rows
            if fetch == "one":
                return cur.fetchone()
            if fetch == "count":
                return cur.rowcount
            c.commit()
            return None
    finally:
        release(c)


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    object_type TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    base_url TEXT NOT NULL,
    marker_color TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS houses (
    id SERIAL PRIMARY KEY,
    object_type TEXT NOT NULL REFERENCES sources(object_type),
    source_id TEXT,
    source_url TEXT,
    title TEXT,
    region TEXT,
    district TEXT,
    council TEXT,
    locality TEXT,
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    price NUMERIC(14,2),
    price_note TEXT,
    sale_method TEXT,
    area_total NUMERIC,
    area_land NUMERIC,
    rooms INTEGER,
    floors INTEGER,
    description TEXT,
    status TEXT,
    first_seen TIMESTAMPTZ DEFAULT now(),
    last_seen TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (object_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_houses_geom ON houses (latitude, longitude) WHERE latitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_houses_type ON houses (object_type);
CREATE INDEX IF NOT EXISTS idx_houses_region ON houses (region);

CREATE TABLE IF NOT EXISTS photos (
    id SERIAL PRIMARY KEY,
    house_id INTEGER NOT NULL REFERENCES houses(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    local_path TEXT,
    ordr INTEGER DEFAULT 0,
    downloaded BOOLEAN DEFAULT false,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_photos_house ON photos (house_id);

CREATE TABLE IF NOT EXISTS parse_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    profile TEXT,
    status TEXT,
    source_filter TEXT,
    objects_found INTEGER DEFAULT 0,
    objects_new INTEGER DEFAULT 0,
    objects_updated INTEGER DEFAULT 0,
    photos_downloaded INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_started ON parse_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS parse_logs (
    id BIGSERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES parse_runs(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ DEFAULT now(),
    level TEXT,
    source TEXT,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_run ON parse_logs (run_id, ts);

CREATE TABLE IF NOT EXISTS kv_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def migrate():
    c = conn()
    try:
        with c.cursor() as cur:
            for stmt in SCHEMA.split(";"):
                s = stmt.strip()
                if s:
                    cur.execute(s)
        c.commit()
        # seed sources from config
        sources = config.get("parser.sources", {})
        for key, src in sources.items():
            cur_args = (
                src.get("object_type", key),
                src.get("label", key),
                src.get("base_url"),
                src.get("marker_color", "#888888"),
            )
            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sources (object_type, label, base_url, marker_color)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (object_type) DO UPDATE SET
                        label = EXCLUDED.label,
                        base_url = EXCLUDED.base_url,
                        marker_color = EXCLUDED.marker_color
                    """,
                    cur_args,
                )
        c.commit()
    finally:
        release(c)

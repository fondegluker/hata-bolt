import datetime as dt
import json
import os
import queue
import threading
import time

from app import config, db

_RUN_LOCK = threading.Lock()
_state = {
    "run_id": None,
    "active": False,
    "stop": False,
    "phase": "idle",
    "progress": 0,
    "total": 0,
    "processed": 0,
    "new": 0,
    "updated": 0,
    "photos": 0,
    "errors": 0,
    "started_at": None,
    "source": None,
    "profile": None,
}
_thread = None


def status():
    return dict(_state)


def request_stop():
    _state["stop"] = True


def log_file_path():
    d = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "parser.log")


class Logger:
    def __init__(self, run_id):
        self.run_id = run_id
        self.path = log_file_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._f = open(self.path, "a", encoding="utf-8")
        self._q = db.conn()

    def _db_log(self, level, source, message):
        try:
            with self._q.cursor() as cur:
                cur.execute(
                    "INSERT INTO parse_logs (run_id, level, source, message) VALUES (%s,%s,%s,%s)",
                    (self.run_id, level, source, message),
                )
            self._q.commit()
        except Exception:
            try:
                self._q.rollback()
            except Exception:
                pass

    def log(self, level, message, source="parser"):
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] [{source}] {message}"
        self._f.write(line + "\n")
        self._f.flush()
        self._db_log(level, source, message)

    def info(self, m, source="parser"):
        self.log("INFO", m, source)

    def warn(self, m, source="parser"):
        self.log("WARN", m, source)

    def error(self, m, source="parser"):
        self.log("ERROR", m, source)

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass
        try:
            db.release(self._q)
        except Exception:
            pass


def _new_run(profile, source_filter):
    c = db.conn()
    try:
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO parse_runs (profile, status, source_filter) VALUES (%s,'running',%s) RETURNING id",
                (profile, source_filter),
            )
            rid = cur.fetchone()[0]
        c.commit()
        return rid
    finally:
        db.release(c)


def _finish_run(run_id, st):
    c = db.conn()
    try:
        with c.cursor() as cur:
            cur.execute(
                """UPDATE parse_runs SET
                   finished_at = now(), status = %s,
                   objects_found = %s, objects_new = %s, objects_updated = %s,
                   photos_downloaded = %s, errors = %s, notes = %s
                 WHERE id = %s""",
                (
                    st,
                    _state["total"],
                    _state["new"],
                    _state["updated"],
                    _state["photos"],
                    _state["errors"],
                    _state.get("phase"),
                    run_id,
                ),
            )
        c.commit()
    finally:
        db.release(c)


def logs(run_id, since=0):
    if run_id is None:
        return []
    rows = db.query(
        "SELECT id, ts, level, source, message FROM parse_logs WHERE run_id = %s AND id > %s ORDER BY id ASC",
        (run_id, since),
    )
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "ts": r["ts"].isoformat() if r["ts"] else None,
                "level": r["level"],
                "source": r["source"],
                "message": r["message"],
            }
        )
    return out


def start_run(source_filter="all", profile_override=None, dry_run=False):
    global _thread
    with _RUN_LOCK:
        if _state["active"]:
            return _state["run_id"]
        profile = profile_override or config.get("parser.active_profile", "balanced")
        run_id = _new_run(profile, source_filter)
        _state.update(
            run_id=run_id,
            active=True,
            stop=False,
            phase="starting",
            progress=0,
            total=0,
            processed=0,
            new=0,
            updated=0,
            photos=0,
            errors=0,
            started_at=dt.datetime.now().isoformat(),
            source=source_filter,
            profile=profile,
        )
        _thread = threading.Thread(
            target=_run_thread, args=(run_id, profile, source_filter, dry_run), daemon=True
        )
        _thread.start()
        return run_id


def _run_thread(run_id, profile, source_filter, dry_run):
    logger = Logger(run_id)
    try:
        from app.parser.engine import Engine

        eng = Engine(profile, source_filter, dry_run, logger, _state)
        eng.run()
        final = "completed" if not _state["stop"] else "stopped"
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fatal: {e}", source="engine")
        final = "error"
    finally:
        _state["active"] = False
        _state["phase"] = final
        _finish_run(run_id, final)
        logger.info(f"Run finished: {final}", source="runtime")
        logger.close()

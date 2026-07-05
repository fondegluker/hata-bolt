import os

from flask import Blueprint, abort, jsonify, request

from app import config, houses
from app.parser import runtime

bp = Blueprint("api", __name__)


@bp.route("/houses")
def api_houses():
    object_type = request.args.get("object_type") or None
    region = request.args.get("region") or None
    sale_method = request.args.get("sale_method") or None
    rows = houses.houses_geo(object_type, region, sale_method)
    return jsonify([dict(r) for r in rows])


@bp.route("/house/<int:house_id>")
def api_house(house_id):
    h = houses.get_house(house_id)
    if not h:
        abort(404)
    return jsonify(_serialise_house(h))


def _serialise_house(h):
    out = dict(h)
    if out.get("price") is not None:
        out["price"] = float(out["price"])
    for k in ("area_total", "area_land"):
        if out.get(k) is not None:
            out[k] = float(out[k])
    if out.get("first_seen"):
        out["first_seen"] = out["first_seen"].isoformat()
    if out.get("last_seen"):
        out["last_seen"] = out["last_seen"].isoformat()
    out["photos"] = [dict(p) for p in out.get("photos", [])]
    return out


@bp.route("/regions")
def api_regions():
    return jsonify([dict(r) for r in houses.regions()])


@bp.route("/stats")
def api_stats():
    return jsonify(_stats_serialised())


def _stats_serialised():
    s = houses.stats()
    for r in s.get("recent_runs", []):
        if r.get("started_at"):
            r["started_at"] = r["started_at"].isoformat()
        if r.get("finished_at"):
            r["finished_at"] = r["finished_at"].isoformat()
    return s


@bp.route("/parse/start", methods=["POST"])
def api_parse_start():
    body = request.get_json(silent=True) or {}
    source_filter = body.get("source") or "all"
    profile_override = body.get("profile")
    dry = bool(body.get("dry_run", config.get("parser.dry_run", False)))
    run_id = runtime.start_run(source_filter, profile_override, dry)
    return jsonify({"run_id": run_id, "status": "started"})


@bp.route("/parse/active")
def api_parse_active():
    st = runtime.status()
    return jsonify(st)


@bp.route("/parse/stop", methods=["POST"])
def api_parse_stop():
    runtime.request_stop()
    return jsonify({"status": "stop_requested"})


@bp.route("/parse/logs")
def api_parse_logs():
    run_id = request.args.get("run_id", type=int)
    since = request.args.get("since", 0, type=int)
    rows = runtime.logs(run_id, since)
    return jsonify(rows)


@bp.route("/parse/logfile")
def api_parse_logfile():
    path = os.path.abspath(runtime.log_file_path())
    if not os.path.exists(path):
        return ("", 404)
    with open(path, "r", encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.route("/settings", methods=["GET"])
def api_settings_get():
    return jsonify(config.all())


@bp.route("/settings", methods=["POST"])
def api_settings_set():
    body = request.get_json(silent=True) or {}
    updates = body.get("updates") if isinstance(body, dict) else None
    if not isinstance(updates, dict):
        return jsonify({"error": "expected {updates: {path: value}}"}), 400
    for path, val in updates.items():
        config.set(path, val)
    return jsonify(config.all())

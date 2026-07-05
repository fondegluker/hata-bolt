from flask import Blueprint, render_template

from app import config, houses

bp = Blueprint("pages", __name__)


@bp.context_processor
def inject_globals():
    return {
        "app_config": config.all(),
        "theme": config.get("app.theme", "dark"),
        "map_cfg": config.get("map"),
    }


@bp.route("/")
def dashboard():
    return render_template("dashboard.html", stats=houses.stats(), sources=houses.list_sources())


@bp.route("/map")
def map_page():
    sources = houses.list_sources()
    regions = houses.regions()
    return render_template("map.html", sources=sources, regions=regions)


@bp.route("/parser")
def parser_page():
    profiles = config.get("parser.profiles")
    active = config.get("parser.active_profile")
    sources = config.get("parser.sources")
    last = houses.stats().get("recent_runs", [])
    return render_template(
        "parser.html", profiles=profiles, active=active, sources=sources, last_runs=last
    )


@bp.route("/settings")
def settings_page():
    return render_template("settings.html", full=config.all())

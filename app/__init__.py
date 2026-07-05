import os

from flask import Flask, send_from_directory
from app import config, db


def create_app(env="production"):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["DEBUG"] = bool(config.get("app.debug", False))
    app.config["ENV"] = env
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

    # photos are served from the data dir
    photo_dir = os.path.abspath(os.path.join(app.root_path, "..", config.get("parser.photo_dir", "data/photos")))

    @app.route("/photos/<path:filename>")
    def serve_photo(filename):
        return send_from_directory(photo_dir, filename)

    # register blueprints
    from app.api.views import bp as api_bp
    from app.pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # migrate on boot so a fresh DB is usable immediately
    try:
        db.migrate()
    except Exception as e:  # noqa: BLE001
        app.logger.warning("DB migrate failed (DB not ready yet?): %s", e)

    return app

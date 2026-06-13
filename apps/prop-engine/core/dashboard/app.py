"""Flask dashboard factory."""
import sys
from pathlib import Path
from flask import Flask, send_from_directory

APP_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(APP_ROOT))


def create_app(snapshot_path: str = None, db_path: str = None) -> Flask:
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent / "static"),
        static_url_path="/static",
    )

    app.config["SNAPSHOT_PATH"] = snapshot_path or str(
        APP_ROOT / "core" / "dashboard" / "static" / "data" / "today.json"
    )
    app.config["DB_PATH"] = db_path or str(APP_ROOT / "data" / "prop_engine.db")
    app.config["APP_ROOT"] = str(APP_ROOT)

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.route("/_shared/<path:filename>")
    def shared_assets(filename):
        return send_from_directory(str(APP_ROOT.parent.parent / "_shared"), filename)

    @app.route("/_skills/<path:filename>")
    def skill_assets(filename):
        return send_from_directory(str(APP_ROOT.parent.parent / "_skills"), filename)

    from core.dashboard.api import register_api
    register_api(app)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)

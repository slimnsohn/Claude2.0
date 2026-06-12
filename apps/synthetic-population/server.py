import sys
from pathlib import Path
from flask import Flask

sys.path.insert(0, str(Path(__file__).parent))

def create_app(data_dir: str = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["DATA_DIR"] = Path(data_dir) if data_dir else Path(__file__).parent / "data"

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    # Initialize opinion engine (loads CES data once, caches in memory)
    ces_path = app.config["DATA_DIR"] / "raw" / "ces" / "ces_2024_common.csv"
    if ces_path.exists():
        from engine.opinion import OpinionEngine
        app.config["OPINION_ENGINE"] = OpinionEngine(str(ces_path))
    else:
        app.config["OPINION_ENGINE"] = None

    @app.route("/_shared/<path:filename>")
    def shared_assets(filename):
        shared_dir = Path(__file__).parent.parent.parent / "_shared"
        from flask import send_from_directory
        return send_from_directory(str(shared_dir), filename)

    @app.route("/_skills/<path:filename>")
    def skill_assets(filename):
        skills_dir = Path(__file__).parent.parent.parent / "_skills"
        from flask import send_from_directory
        return send_from_directory(str(skills_dir), filename)

    # Register API blueprints
    from api import register_blueprints
    register_blueprints(app)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)

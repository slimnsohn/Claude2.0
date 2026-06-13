"""Dashboard API endpoints."""
import json
import subprocess
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app
from core.storage import StorageBackend


def register_api(app):
    bp = Blueprint("api", __name__, url_prefix="/api")

    def _storage():
        return StorageBackend(current_app.config["DB_PATH"])

    @bp.get("/plays")
    def plays():
        path = Path(current_app.config["SNAPSHOT_PATH"])
        if not path.exists():
            return jsonify({"run_id": None, "n_plays": 0, "plays": [],
                            "generated_at": None})
        return jsonify(json.loads(path.read_text()))

    @bp.get("/markets/<int:market_id>")
    def market_detail(market_id):
        st = _storage()
        return jsonify({"market_id": market_id,
                        "lines": st.latest_book_lines(market_id)})

    @bp.post("/log_bet")
    def log_bet():
        body = request.get_json(force=True)
        play_id = body.get("play_id")
        if play_id is None:
            return jsonify({"error": "play_id required"}), 400
        st = _storage()
        with st._conn() as c:
            row = c.execute(
                "SELECT id FROM plays WHERE id = ?", (play_id,)
            ).fetchone()
        if not row:
            return jsonify({"error": "play not found"}), 404
        bet_id = st.log_bet(
            play_id=play_id,
            stake_actual=float(body["stake_actual"]),
            odds_actual=int(body["odds_actual"]),
            book=body["book"],
            notes=body.get("notes", ""),
        )
        return jsonify({"bet_id": bet_id})

    @bp.get("/bets")
    def bets():
        return jsonify({"bets": _storage().all_bets()})

    @bp.post("/bets/<int:bet_id>/settle")
    def settle(bet_id):
        body = request.get_json(force=True)
        _storage().settle_bet(
            bet_id, result=body["result"], profit=float(body["profit"])
        )
        return jsonify({"ok": True})

    @bp.post("/refresh")
    def refresh():
        app_root = current_app.config["APP_ROOT"]
        rc = subprocess.run(
            ["python", "cli.py", "wnba"], cwd=app_root,
        ).returncode
        return jsonify({"ok": rc == 0, "returncode": rc})

    app.register_blueprint(bp)

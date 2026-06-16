#!/usr/bin/env python
"""Flask app for the Fantasy Basketball web UI.

Thin layer: opens a READ-ONLY DuckDB connection per request and calls the
tested fbball.webapi functions. Serves the single-page UI from web/ and mounts
the workspace's shared CSS + chat widget so there's no asset duplication.

Run:  python app.py   (or start.bat)
"""

import os
import subprocess
import sys

import duckdb
from flask import Flask, Response, jsonify, request, send_from_directory

from fbball import db, ingest, webapi

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(APP_DIR))
SHARED_DIR = os.path.join(WORKSPACE, "_shared")
WIDGET_DIR = os.path.join(WORKSPACE, "_skills", "llm-chat-widget", "dist")
WEB_DIR = os.path.join(APP_DIR, "web")
DEFAULT_DB = os.path.join(APP_DIR, "data", "fbball.duckdb")


def create_app(db_path: str = DEFAULT_DB) -> Flask:
    app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")

    # Ensure schema/views exist once (read-only connections can't create them).
    _c = duckdb.connect(db_path)
    db.init_schema(_c)
    _c.close()

    def con():
        return duckdb.connect(db_path, read_only=True)

    def run(fn, *a, **k):
        c = con()
        try:
            return jsonify(fn(c, *a, **k))
        finally:
            c.close()

    # ---- pages + shared assets ----
    @app.route("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.route("/shared/<path:p>")
    def shared(p):
        return send_from_directory(SHARED_DIR, p)

    @app.route("/widget/<path:p>")
    def widget(p):
        return send_from_directory(WIDGET_DIR, p)

    # ---- API ----
    @app.route("/api/overview")
    def overview():
        return run(webapi.overview)

    @app.route("/api/players")
    def players():
        return run(webapi.players, search=request.args.get("search", ""),
                   season=request.args.get("season") or None)

    @app.route("/api/player/<int:pid>/seasons")
    def player_seasons(pid):
        return run(webapi.player_seasons, pid)

    @app.route("/api/rankings")
    def rankings():
        return run(webapi.rankings,
                   source=request.args.get("source", "season"),
                   punt=request.args.getlist("punt"),
                   pos=request.args.get("pos") or None,
                   min_gp=int(request.args.get("min_gp", 20)))

    @app.route("/api/draft/board")
    def draft_board():
        return run(webapi.draft_board,
                   source=request.args.get("source", "projection"),
                   punt=request.args.getlist("punt"),
                   pos=request.args.get("pos") or None)

    @app.route("/api/draft/recommend", methods=["POST"])
    def draft_recommend():
        body = request.get_json(force=True, silent=True) or {}
        return run(webapi.draft_recommend,
                   drafted_ids=body.get("drafted_ids", []),
                   my_ids=body.get("my_ids", []),
                   source=body.get("source", "projection"),
                   punt=body.get("punt", []))

    @app.route("/api/league/rosters")
    def league_rosters():
        return run(webapi.league_rosters)

    @app.route("/api/league/seasons")
    def league_seasons():
        return run(webapi.league_seasons)

    @app.route("/api/league/standings")
    def league_standings():
        s = request.args.get("season")
        return run(webapi.league_standings, season=int(s) if s else None)

    @app.route("/api/league/champions")
    def league_champions():
        return run(webapi.league_champions)

    @app.route("/api/league/owners")
    def league_owners():
        return run(webapi.league_owners)

    @app.route("/api/league/draft")
    def league_draft():
        s = request.args.get("season")
        return run(webapi.league_draft, season=int(s) if s else None)

    # ---- update / refresh ----
    @app.route("/api/update/state")
    def update_state():
        return run(webapi.update_state)

    @app.route("/api/update/stream")
    def update_stream():
        """Stream a refresh (Server-Sent Events). Runs ingest.py refresh in a
        separate process so the write is isolated from read-only serving."""
        raw = request.args.get("steps", "")
        steps = [s for s in raw.split(",") if s in ingest.REFRESH_STEPS]
        cmd = [sys.executable, "-u", os.path.join(APP_DIR, "ingest.py"), "refresh"]
        if steps:
            cmd += ["--steps", *steps]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

        def gen():
            proc = subprocess.Popen(
                cmd, cwd=APP_DIR, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1)
            for line in proc.stdout:
                yield f"data: {line.rstrip()}\n\n"
            proc.wait()
            yield f"data: ::exit::{proc.returncode}\n\n"

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5050, debug=False)

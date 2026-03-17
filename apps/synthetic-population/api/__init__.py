def register_blueprints(app):
    """Register all API blueprints. Add new blueprints here as they're created."""
    from api.stats import stats_bp
    app.register_blueprint(stats_bp)
    from api.profiles import profiles_bp
    app.register_blueprint(profiles_bp)
    from api.snapshots import snapshots_bp
    app.register_blueprint(snapshots_bp)
    from api.events_api import events_bp
    app.register_blueprint(events_bp)

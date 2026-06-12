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
    from api.polls import polls_bp
    app.register_blueprint(polls_bp)
    from api.sources import sources_bp
    app.register_blueprint(sources_bp)
    from api.world_updates import world_updates_bp
    app.register_blueprint(world_updates_bp)
    from api.benchmarks import benchmarks_bp
    app.register_blueprint(benchmarks_bp)
    from api.polymarket import polymarket_bp
    app.register_blueprint(polymarket_bp)

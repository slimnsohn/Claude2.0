"""Configuration loading + the live-mode arming interlock.

Live trading requires BOTH `mode: live` + `live_armed: true` in the YAML AND
the auth env vars present. Anything less refuses to start with a clear error
— a half-configured system must fail loudly, not trade quietly.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

VALID_MODES = ("backtest", "paper", "live")


class ConfigError(Exception):
    pass


class DashboardConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    control_token: str = ""


class Config(BaseModel):
    mode: str = "paper"
    live_armed: bool = False
    bankroll: float = Field(default=1000.0, gt=0)
    double_or_bust: bool = True
    dashboard: DashboardConfig = DashboardConfig()
    strategies: dict = Field(default_factory=lambda: {
        "s1_arb": {"enabled": True}, "s2_mm": {"enabled": True},
        "s3_crypto": {"enabled": True}, "s4_calib": {"enabled": True}})
    risk: dict = Field(default_factory=dict)
    poll_seconds: float = 5.0
    market_refresh_seconds: float = 3600.0
    max_tracked_markets: int = 60


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"bad yaml in {path}: {exc}") from exc
    try:
        cfg = Config(**raw)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc

    if cfg.mode not in VALID_MODES:
        raise ConfigError(f"mode must be one of {VALID_MODES}, got {cfg.mode!r}")

    if cfg.mode == "live":
        if not cfg.live_armed:
            raise ConfigError(
                "mode: live requires live_armed: true — this is the explicit "
                "two-key interlock for real money")
        missing = [v for v in ("POLYMARKET_PRIVATE_KEY",
                               "POLYMARKET_FUNDER_ADDRESS")
                   if not os.environ.get(v)]
        if missing:
            raise ConfigError(f"live mode requires env vars: {missing}")
    return cfg

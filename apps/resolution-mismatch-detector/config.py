"""Configuration constants and thresholds."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "db" / "mismatch.db"
REPORTS_DIR = PROJECT_ROOT / "reports"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"

# Load .env if present
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Kalshi RSA-PSS auth (no Anthropic key needed — uses Claude Code CLI)
KALSHI_API_KEY = os.environ.get("KALSHI_API_KEY", "")
KALSHI_PRIVATE_KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "./kalshi-private-key.pem")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Analysis thresholds
MIN_VOLUME_THRESHOLD = 10_000
HIGH_SEVERITY_PRICE_THRESHOLD = 0.70
ANALYSIS_BATCH_SIZE = 50
CROSS_PLATFORM_MATCH_THRESHOLD = 0.65
MAX_DAILY_CLAUDE_CALLS = 500  # soft cap on CLI calls per day
SOURCE_POLL_INTERVAL_HOURS = 6

# API settings
POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"
KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_PAGE_DELAY_S = 0.2
KALSHI_REQUEST_DELAY_S = 1.0

# Claude Code CLI model (passed to `claude -p --model`)
CLAUDE_CLI_MODEL = "sonnet"

# Scoring
SEVERITY_WEIGHTS = {"high": 1.0, "medium": 0.6, "low": 0.3, "none": 0.0}
LIQUIDITY_LOG_CAP = 6  # log10(1M)
POSITION_MULTIPLIER = 2.0

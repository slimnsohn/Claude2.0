import pytest

from pmtrader.config import ConfigError, load_config

GOOD = """
mode: paper
bankroll: 500.0
double_or_bust: true
dashboard:
  host: 127.0.0.1
  port: 8765
  control_token: "secret-token"
strategies:
  s1_arb: {enabled: true}
  s2_mm: {enabled: true}
  s3_crypto: {enabled: true}
  s4_calib: {enabled: true}
risk: {}
"""


def write(tmp_path, text):
    p = tmp_path / "settings.yaml"
    p.write_text(text)
    return p


class TestLoad:
    def test_good_config(self, tmp_path):
        cfg = load_config(write(tmp_path, GOOD))
        assert cfg.mode == "paper"
        assert cfg.bankroll == 500.0
        assert cfg.strategies["s1_arb"]["enabled"] is True
        assert cfg.dashboard.port == 8765

    def test_bad_mode_rejected(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(write(tmp_path, GOOD.replace("mode: paper", "mode: yolo")))

    def test_default_mode_is_paper(self, tmp_path):
        cfg = load_config(write(tmp_path, GOOD.replace("mode: paper\n", "")))
        assert cfg.mode == "paper"

    def test_negative_bankroll_rejected(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(write(tmp_path, GOOD.replace("bankroll: 500.0",
                                                     "bankroll: -5")))


class TestLiveGuards:
    def test_live_requires_armed_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "k")
        monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "f")
        with pytest.raises(ConfigError, match="live_armed"):
            load_config(write(tmp_path, GOOD.replace("mode: paper", "mode: live")))

    def test_live_requires_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("POLYMARKET_FUNDER_ADDRESS", raising=False)
        text = GOOD.replace("mode: paper", "mode: live\nlive_armed: true")
        with pytest.raises(ConfigError, match="env"):
            load_config(write(tmp_path, text))

    def test_live_fully_armed_loads(self, tmp_path, monkeypatch):
        monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "k")
        monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "f")
        text = GOOD.replace("mode: paper", "mode: live\nlive_armed: true")
        cfg = load_config(write(tmp_path, text))
        assert cfg.mode == "live"

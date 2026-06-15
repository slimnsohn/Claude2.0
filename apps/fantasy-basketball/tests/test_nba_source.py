import pytest

from fbball import nba_source


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}
    sleeps = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("timeout")
        return "ok"

    result = nba_source._retry(
        flaky, attempts=5, base_delay=1.0, sleeper=sleeps.append
    )
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_uses_exponential_backoff():
    sleeps = []

    def flaky():
        raise ConnectionError("timeout")

    with pytest.raises(ConnectionError):
        nba_source._retry(
            flaky, attempts=3, base_delay=1.0, sleeper=sleeps.append
        )
    # backoff between the 3 attempts: 1s then 2s (exponential), no sleep after last
    assert sleeps == [1.0, 2.0]


def test_retry_raises_after_exhausting_attempts():
    def always_fails():
        raise ConnectionError("timeout")

    with pytest.raises(ConnectionError):
        nba_source._retry(
            always_fails, attempts=2, base_delay=0.1, sleeper=lambda _: None
        )

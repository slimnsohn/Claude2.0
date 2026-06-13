"""Unit tests for the API rate limiter (no HTTP, injected clock)."""
from tool.api.auth import RateLimiter


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_allows_up_to_limit_then_blocks():
    clk = FakeClock()
    rl = RateLimiter(clock=clk)
    assert rl.allow("k", limit=3)
    assert rl.allow("k", limit=3)
    assert rl.allow("k", limit=3)
    assert not rl.allow("k", limit=3)   # 4th in the window is blocked


def test_window_slides():
    clk = FakeClock()
    rl = RateLimiter(clock=clk)
    assert rl.allow("k", limit=1)
    assert not rl.allow("k", limit=1)
    clk.t += 61                          # past the 60s window
    assert rl.allow("k", limit=1)        # old hit expired


def test_keys_are_independent():
    rl = RateLimiter(clock=FakeClock())
    assert rl.allow("a", limit=1)
    assert rl.allow("b", limit=1)        # different key unaffected
    assert not rl.allow("a", limit=1)


def test_reset_clears_state():
    clk = FakeClock()
    rl = RateLimiter(clock=clk)
    rl.allow("k", limit=1)
    rl.reset()
    assert rl.allow("k", limit=1)        # state cleared

from fbball import ingest


def _fake_runners(calls):
    def make(name):
        def run(con, log):
            calls.append(name)
            log(f"  {name}: working")
            return f"{name} ok"
        return run
    return {name: make(name) for name in ingest.REFRESH_STEPS}


def test_run_refresh_runs_all_steps_in_canonical_order():
    calls, logs = [], []
    ingest.run_refresh(None, log=logs.append, runners=_fake_runners(calls))
    assert calls == ingest.REFRESH_STEPS            # all, in order
    assert "::step::logs" in logs
    assert "::done::logs::logs ok" in logs


def test_run_refresh_runs_only_selected_steps_in_order():
    calls, logs = [], []
    ingest.run_refresh(None, steps=["ages", "logs"], log=logs.append,
                       runners=_fake_runners(calls))
    assert calls == ["logs", "ages"]                # canonical order preserved
    assert "::step::history" not in logs            # unselected step skipped


def test_run_refresh_reports_completion():
    logs = []
    ingest.run_refresh(None, steps=["live"], log=logs.append,
                       runners=_fake_runners([]))
    assert any(l.startswith("::complete::") for l in logs)


def test_invalid_step_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        ingest.run_refresh(None, steps=["bogus"], log=lambda _: None,
                           runners=_fake_runners([]))

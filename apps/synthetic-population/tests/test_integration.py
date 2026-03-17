"""Full pipeline integration smoke test."""
import pytest
import json
import numpy as np
import pandas as pd
from pathlib import Path


class TestFullPipeline:
    """End-to-end smoke test with small synthetic data."""

    @pytest.fixture
    def workspace(self, tmp_path):
        """Set up temp workspace with all needed directories."""
        for d in ["models", "profiles", "events", "polls"]:
            (tmp_path / d).mkdir()
        return tmp_path

    @pytest.fixture
    def backbone(self):
        """20-record ACS-like demographic backbone."""
        np.random.seed(42)
        n = 20
        return pd.DataFrame({
            "age": np.random.randint(20, 75, n),
            "age_bracket": np.random.choice(
                ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"], n
            ),
            "sex": np.random.choice(["M", "F"], n),
            "race": np.random.choice(
                ["white", "black", "hispanic", "asian"], n, p=[0.6, 0.13, 0.19, 0.08]
            ),
            "education": np.random.choice(
                ["hs_diploma", "some_college", "bachelors", "graduate"], n
            ),
            "income_bracket": np.random.choice(
                ["25-50k", "50-75k", "75-100k", "100-150k"], n
            ),
            "state": np.random.choice(["MI", "OH", "GA", "TX", "CA", "NY"], n),
            "urban_rural": np.random.choice(["urban", "suburban", "rural"], n),
            "marital_status": np.random.choice(
                ["married", "divorced", "never_married"], n
            ),
            # Use a small set of income values to avoid SDV detecting it as primary key
            "income": np.random.choice([30000, 45000, 55000, 70000, 85000, 100000, 120000], n),
            "occupation": np.random.choice(
                ["teacher", "engineer", "nurse", "mechanic", "manager"], n
            ),
            "children_count": np.random.randint(0, 4, n),
            "religion_affiliation": np.random.choice(
                ["evangelical", "mainline", "catholic", "none"], n
            ),
            "religion_attendance": np.random.choice(["weekly", "monthly", "never"], n),
            "income_source": np.random.choice(
                ["wages", "self_employment"], n, p=[0.85, 0.15]
            ),
        })

    @pytest.fixture
    def donor(self):
        """30-record CES-like political donor."""
        np.random.seed(123)
        n = 30
        return pd.DataFrame({
            "age_bracket": np.random.choice(
                ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"], n
            ),
            "sex": np.random.choice(["M", "F"], n),
            "race": np.random.choice(
                ["white", "black", "hispanic", "asian"], n
            ),
            "education": np.random.choice(
                ["hs_diploma", "some_college", "bachelors", "graduate"], n
            ),
            "party_id": np.random.choice(
                ["strong_dem", "lean_dem", "independent", "lean_rep", "strong_rep"], n
            ),
            "ideology": np.random.choice([1, 2, 3, 4, 5, 6, 7], n),
            "vote_2024": np.random.choice(
                ["harris", "trump", "other", "did_not_vote"], n
            ),
        })

    def test_step1_fusion(self, backbone, donor):
        """Step 1-2: Fuse backbone + donor via StatisticalMatcher."""
        from pipeline.fuse import StatisticalMatcher

        matcher = StatisticalMatcher(
            match_keys=["age_bracket", "sex", "race", "education"]
        )
        fused = matcher.match(
            backbone, donor, variables=["party_id", "ideology", "vote_2024"]
        )

        # Fused result keeps backbone length, gains donor variables
        assert len(fused) == len(backbone)
        assert "party_id" in fused.columns
        assert "ideology" in fused.columns
        assert "vote_2024" in fused.columns
        # All original backbone columns still present
        for col in backbone.columns:
            assert col in fused.columns

    def test_step2_model_fit_and_generate(self, backbone, donor, workspace):
        """Steps 3-6: Fit model, generate profiles, verify dedup + archetypes + backstory."""
        from pipeline.fuse import StatisticalMatcher
        from pipeline.fit_model import ModelTrainer
        from generator.generate import ProfileGenerator
        from generator.dedup import DedupChecker

        # --- Fuse ---
        matcher = StatisticalMatcher(
            match_keys=["age_bracket", "sex", "race", "education"]
        )
        fused = matcher.match(
            backbone, donor, variables=["party_id", "ideology", "vote_2024"]
        )

        # --- Fit model ---
        categorical = [c for c in fused.columns if fused[c].dtype == "object"]
        numerical = [
            c for c in fused.columns
            if fused[c].dtype in ["int64", "float64", "int32"]
        ]
        trainer = ModelTrainer()
        trainer.fit(fused, categorical_columns=categorical, numerical_columns=numerical)

        model_path = str(workspace / "models" / "test.pkl")
        trainer.save(model_path)
        assert Path(model_path).exists()

        # --- Generate first batch (10 profiles) ---
        registry_path = str(workspace / "profiles" / "registry.json")
        gen = ProfileGenerator(model_path, registry_path)
        profiles = gen.generate_batch(10, batch_name="integration-test")

        assert len(profiles) == 10
        assert all("profile_id" in p for p in profiles)
        assert all("backstory" in p for p in profiles)
        assert all("archetype_id" in p for p in profiles)
        # Backstory should be a meaningful paragraph
        assert all(len(p["backstory"]) > 20 for p in profiles)
        # drift_log initialized
        assert all("drift_log" in p for p in profiles)

        # --- Dedup check: generate more, verify no exact ID duplicates ---
        # Note: with a small synthetic dataset, dedup may reject some candidates
        # so we may get fewer than requested. The key check is uniqueness.
        gen2 = ProfileGenerator(model_path, registry_path)
        profiles2 = gen2.generate_batch(10, batch_name="integration-test-2")

        assert len(profiles2) > 0, "Second batch should produce at least some profiles"
        all_ids = [p["profile_id"] for p in profiles] + [p["profile_id"] for p in profiles2]
        assert len(all_ids) == len(set(all_ids)), "Duplicate profile_ids found"

        # Registry should contain all profiles from both batches
        with open(registry_path) as f:
            registry = json.load(f)
        assert len(registry) == len(profiles) + len(profiles2)

    def test_step3_polling_and_events(self, backbone, donor, workspace):
        """Steps 9-13: Poll prompts, events, drift."""
        from pipeline.fuse import StatisticalMatcher
        from pipeline.fit_model import ModelTrainer
        from generator.generate import ProfileGenerator
        from engine.poll import PollRunner
        from engine.prompts import build_poll_prompt
        from monitor.events import EventStore
        from monitor.drift import DriftEngine
        from generator.archetypes import ArchetypeBuilder

        # --- Set up profiles (abbreviated pipeline) ---
        matcher = StatisticalMatcher(
            match_keys=["age_bracket", "sex", "race", "education"]
        )
        fused = matcher.match(
            backbone, donor, variables=["party_id", "ideology", "vote_2024"]
        )
        categorical = [c for c in fused.columns if fused[c].dtype == "object"]
        numerical = [
            c for c in fused.columns
            if fused[c].dtype in ["int64", "float64", "int32"]
        ]
        trainer = ModelTrainer()
        trainer.fit(fused, categorical_columns=categorical, numerical_columns=numerical)
        model_path = str(workspace / "models" / "test2.pkl")
        trainer.save(model_path)
        registry_path = str(workspace / "profiles" / "registry2.json")
        gen = ProfileGenerator(model_path, registry_path)
        profiles = gen.generate_batch(10)

        # --- Verify archetypes assigned by generator ---
        assert all("archetype_id" in p for p in profiles)
        assert all(
            p["archetype_id"] is not None and p["archetype_id"].startswith("A-")
            for p in profiles
        )

        # --- Get archetype weights for polling ---
        df = pd.DataFrame(profiles)
        builder = ArchetypeBuilder(min_cell_size=2)
        df = builder.build(df)
        weights = builder.get_weights()
        assert len(weights) > 0

        # Update profiles with fresh archetype_id from builder
        for i, p in enumerate(profiles):
            p["archetype_id"] = df.iloc[i]["archetype_id"]

        # --- Test build_poll_prompt directly (Step 9-10) ---
        prompt = build_poll_prompt(profiles[0], "Will inflation decrease in 2026?")
        assert isinstance(prompt, str)
        assert "QUESTION:" in prompt
        assert "Will inflation decrease in 2026?" in prompt
        assert "Opinion:" in prompt
        assert "Confidence:" in prompt

        # --- Test PollRunner (Step 9) ---
        runner = PollRunner(polls_dir=str(workspace / "polls"))
        poll_id = runner.prepare(
            "Will inflation decrease in 2026?", profiles, weights
        )
        assert poll_id.startswith("POLL-")

        # Check prompts file exists
        prompts_file = workspace / "polls" / poll_id / "prompts.txt"
        assert prompts_file.exists()
        prompts_content = prompts_file.read_text()
        assert "Will inflation decrease in 2026?" in prompts_content

        # Record some responses
        responded_archetypes = list(weights.keys())[:3]
        for aid in responded_archetypes:
            runner.record_response(aid, "I think so, yes.", opinion="yes", confidence=7)

        result = runner.aggregate()
        assert result["n_responses"] >= 1
        assert "distribution" in result
        assert result["poll_id"] == poll_id

        # --- Test events (Step 11) ---
        store = EventStore(workspace / "events")
        event_id = store.add({
            "date": "2026-03-17",
            "description": "Fed signals rate cut",
            "affected_segments": {
                "party_id": {
                    "lean_rep": {"climate_policy_support": 0.05},
                },
            },
        })
        assert event_id
        assert (workspace / "events" / f"{event_id}.json").exists()

        # Retrieve event
        event = store.get(event_id)
        assert event["description"] == "Fed signals rate cut"

        # --- Test drift (Steps 12-13) ---
        # Add a numeric field for drift to work with
        for p in profiles:
            p["climate_policy_support"] = 0.5
            p["drift_log"] = p.get("drift_log", [])

        # Find a profile with party_id == lean_rep
        affected = [p for p in profiles if p.get("party_id") == "lean_rep"]
        if affected:
            original_value = affected[0]["climate_policy_support"]
            updated = DriftEngine.apply(affected[0], event)
            # climate_policy_support is NOT in IMMUTABLE_VARS or SLOW_VARS,
            # so it should be changed by the delta
            assert updated["climate_policy_support"] == pytest.approx(
                original_value + 0.05
            )
            assert len(updated["drift_log"]) > 0
            assert updated["drift_log"][-1]["event_id"] == event_id
            assert updated["drift_log"][-1]["variable"] == "climate_policy_support"
        else:
            # No lean_rep profiles generated — test drift on a non-matching profile
            # to verify it leaves the profile unchanged
            updated = DriftEngine.apply(profiles[0], event)
            assert updated["climate_policy_support"] == 0.5
            assert len(updated["drift_log"]) == len(profiles[0]["drift_log"])

import json
import uuid
from pathlib import Path
from datetime import datetime
import pandas as pd

from pipeline.fit_model import ModelTrainer
from generator.dedup import DedupChecker
from generator.gap_analysis import GapAnalyzer
from generator.backstory import generate_backstory
from generator.archetypes import ArchetypeBuilder

# Default target marginals (approximate US census)
DEFAULT_MARGINALS = {
    "sex": {"M": 0.49, "F": 0.51},
    "race": {"white": 0.58, "black": 0.12, "hispanic": 0.19, "asian": 0.06, "other": 0.03, "multiracial": 0.02},
    "education": {"less_than_hs": 0.11, "hs_diploma": 0.27, "some_college": 0.20, "bachelors": 0.22, "graduate": 0.13},
}

DEDUP_KEYS = ["age_bracket", "sex", "race", "education", "state", "party_id", "religion_affiliation", "income_source"]


class ProfileGenerator:
    def __init__(self, model_path: str, registry_path: str, marginals: dict = None):
        self.model_path = Path(model_path)
        self.registry_path = Path(registry_path)
        self.marginals = marginals or DEFAULT_MARGINALS
        self.trainer = ModelTrainer()
        self.existing_profiles = []

    def _load_registry(self) -> list[dict]:
        """Load existing profiles from registry JSON."""
        if self.registry_path.exists():
            with open(self.registry_path) as f:
                return json.load(f)
        return []

    def _save_registry(self, profiles: list[dict]):
        """Save profiles to registry JSON."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, 'w') as f:
            json.dump(profiles, f, indent=2, default=str)

    def generate_batch(self, count: int, batch_name: str = None) -> list[dict]:
        """Generate a batch of new profiles."""
        # 1. Load model + existing registry
        self.trainer.load(str(self.model_path))
        self.existing_profiles = self._load_registry()

        # 2. Gap analysis
        existing_df = pd.DataFrame(self.existing_profiles) if self.existing_profiles else pd.DataFrame()
        gap_analyzer = GapAnalyzer(self.marginals)
        # Gap analysis informs but we use SDV's model for actual sampling

        # 3. Sample from model (oversample to account for dedup rejections)
        raw_samples = self.trainer.generate(count * 2)

        # 4. Dedup each candidate
        # Pass a copy so appending to dedup.existing doesn't mutate self.existing_profiles
        dedup = DedupChecker(
            existing_profiles=list(self.existing_profiles),
            composite_keys=DEDUP_KEYS,
            threshold=6
        )

        batch_id = batch_name or f"batch-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        new_profiles = []

        for _, row in raw_samples.iterrows():
            if len(new_profiles) >= count:
                break

            profile = row.to_dict()

            # Check dedup
            if not dedup.is_unique(profile):
                continue

            # Add metadata
            profile["profile_id"] = str(uuid.uuid4())[:8]
            profile["batch_id"] = batch_id
            profile["created_at"] = datetime.now().isoformat()
            profile["updated_at"] = datetime.now().isoformat()
            profile["drift_log"] = []

            # Generate backstory
            profile["backstory"] = generate_backstory(profile)

            new_profiles.append(profile)
            # Add to dedup checker's existing set
            dedup.existing.append(profile)

        # 5. Assign archetypes (on all profiles including new ones)
        all_profiles = self.existing_profiles + new_profiles
        if all_profiles:
            all_df = pd.DataFrame(all_profiles)
            builder = ArchetypeBuilder(min_cell_size=3)
            all_df = builder.build(all_df)
            # Update archetype_id on all profiles
            for i, profile in enumerate(all_profiles):
                profile["archetype_id"] = all_df.iloc[i]["archetype_id"]

        # 6. Save updated registry
        self._save_registry(all_profiles)

        # 7. Report
        print(f"Generated {len(new_profiles)} profiles (batch: {batch_id})")
        print(f"Total registry: {len(all_profiles)} profiles")
        if new_profiles:
            gap_report = gap_analyzer.summary(pd.DataFrame(all_profiles))
            top_gaps = gap_report[:3]
            for g in top_gaps:
                print(f"  Gap: {g['variable']}={g['value']}: target={g['target']:.2f}, actual={g['actual']:.2f}")

        return new_profiles


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate synthetic population profiles")
    parser.add_argument("--count", type=int, required=True, help="Number of profiles to generate")
    parser.add_argument("--batch-name", type=str, default=None, help="Batch name")
    parser.add_argument("--model", type=str, default="data/models/latest.pkl", help="Path to fitted model")
    parser.add_argument("--registry", type=str, default="data/profiles/registry.json", help="Path to profile registry")
    args = parser.parse_args()

    generator = ProfileGenerator(args.model, args.registry)
    profiles = generator.generate_batch(args.count, args.batch_name)

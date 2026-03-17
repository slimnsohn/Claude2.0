import json
from pathlib import Path
from datetime import datetime
from engine.prompts import build_poll_prompt
from engine.aggregate import PollAggregator
from engine.integrity import check_hedge_score, check_consistency


class PollRunner:
    """Orchestrates polling: select archetypes → build prompts → collect → aggregate."""

    def __init__(self, polls_dir: str = "data/polls"):
        self.polls_dir = Path(polls_dir)
        self.polls_dir.mkdir(parents=True, exist_ok=True)
        self.poll_id = None
        self.question = None
        self.prompts = {}  # {archetype_id: prompt_text}
        self.responses = []  # collected responses
        self.archetype_weights = {}
        self.profiles = {}  # {archetype_id: profile_dict}

    def prepare(self, question: str, registry: list[dict], archetype_weights: dict) -> str:
        """
        Select one representative per archetype, build prompts.

        registry: list of profile dicts (must have archetype_id)
        archetype_weights: {archetype_id: float}

        Returns: poll_id
        """
        self.poll_id = f"POLL-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.question = question
        self.archetype_weights = archetype_weights
        self.responses = []

        # Group profiles by archetype, pick first as representative
        by_archetype = {}
        for profile in registry:
            aid = profile.get("archetype_id")
            if aid and aid in archetype_weights and aid not in by_archetype:
                by_archetype[aid] = profile

        # Build prompts
        self.prompts = {}
        self.profiles = {}
        for aid, profile in by_archetype.items():
            self.prompts[aid] = build_poll_prompt(profile, question)
            self.profiles[aid] = profile

        # Save prompts file
        poll_dir = self.polls_dir / self.poll_id
        poll_dir.mkdir(parents=True, exist_ok=True)

        prompts_text = f"# Poll: {question}\n# Generated: {datetime.now().isoformat()}\n\n"
        for aid in sorted(self.prompts.keys()):
            weight = archetype_weights.get(aid, 0)
            prompts_text += f"=== ARCHETYPE {aid} (weight: {weight*100:.1f}%) ===\n"
            prompts_text += self.prompts[aid]
            prompts_text += "\n\n"

        (poll_dir / "prompts.txt").write_text(prompts_text)

        return self.poll_id

    def record_response(self, archetype_id: str, response_text: str,
                        opinion: str = "unsure", confidence: int = 5) -> dict:
        """
        Record and validate a response from an archetype.

        Returns: {archetype_id, response, confidence, hedge_score, flags}
        """
        hedge_score = check_hedge_score(response_text)

        # Check consistency against profile's drift_log
        profile = self.profiles.get(archetype_id, {})
        drift_log = profile.get("drift_log", [])
        new_response = {"topic": self.question, "position": opinion, "confidence": confidence}
        flags = check_consistency(drift_log, new_response)

        result = {
            "archetype_id": archetype_id,
            "response": opinion,
            "confidence": confidence,
            "response_text": response_text,
            "hedge_score": hedge_score,
            "flags": flags,
            "demographics": {
                k: profile.get(k) for k in ["party_id", "race", "education", "urban_rural"]
                if profile.get(k)
            },
        }

        self.responses.append(result)
        return result

    def aggregate(self) -> dict:
        """Run weighted aggregation on collected responses. Save results."""
        agg = PollAggregator(self.archetype_weights)
        result = agg.aggregate(self.responses)
        result["poll_id"] = self.poll_id
        result["question"] = self.question

        # Save results
        if self.poll_id:
            poll_dir = self.polls_dir / self.poll_id
            poll_dir.mkdir(parents=True, exist_ok=True)
            (poll_dir / "results.json").write_text(json.dumps(result, indent=2, default=str))

        return result

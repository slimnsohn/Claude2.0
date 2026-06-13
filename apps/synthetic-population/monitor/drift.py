"""
DriftEngine — applies world events to synthetic population profiles,
updating mutable attitudinal variables while protecting immutable traits.
"""

import copy
from typing import Any


class DriftEngine:
    IMMUTABLE_VARS = {
        "age",
        "race",
        "sex",
        "education",
        "veteran_status",
        "native_born",
    }

    SLOW_VARS = {
        "party_id",
        "religion_affiliation",
        "urban_rural",
        "income_bracket",
    }

    @classmethod
    def apply(cls, profile: dict, event: dict) -> dict:
        """Apply a single event to a profile, returning an updated deep copy.

        Args:
            profile: A synthetic population profile dict. Must contain a
                     'drift_log' list key.
            event:   An event dict with 'event_id' and 'affected_segments'.
                     affected_segments shape:
                       { segment_field: { segment_value: { var: delta } } }

        Returns:
            Updated profile copy with adjusted variables and appended drift_log
            entries for each applied change.
        """
        updated = copy.deepcopy(profile)
        event_id = event.get("event_id", "UNKNOWN")
        affected_segments = event.get("affected_segments", {})

        for segment_field, segment_map in affected_segments.items():
            profile_segment_value = updated.get(segment_field)
            if profile_segment_value not in segment_map:
                # This profile does not belong to an affected segment
                continue

            deltas = segment_map[profile_segment_value]
            for var, delta in deltas.items():
                if var in cls.IMMUTABLE_VARS:
                    continue
                if var in cls.SLOW_VARS:
                    continue

                old_value = updated.get(var)

                if isinstance(delta, (int, float)) and isinstance(old_value, (int, float)):
                    new_value = float(old_value) + float(delta)
                    new_value = max(0.0, min(1.0, new_value))
                else:
                    # String or other type — replace only if not immutable (already checked)
                    new_value = delta

                updated[var] = new_value
                updated["drift_log"].append({
                    "event_id": event_id,
                    "segment_field": segment_field,
                    "segment_value": profile_segment_value,
                    "variable": var,
                    "old_value": old_value,
                    "new_value": new_value,
                    "delta": delta,
                })

        return updated

    @classmethod
    def apply_batch(cls, profiles: list[dict], event: dict) -> list[dict]:
        """Apply an event to a list of profiles.

        Args:
            profiles: List of synthetic population profile dicts.
            event:    Event dict (see apply() for shape).

        Returns:
            New list of updated profile copies.
        """
        return [cls.apply(profile, event) for profile in profiles]

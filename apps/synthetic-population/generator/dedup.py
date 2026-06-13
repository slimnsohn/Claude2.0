class DedupChecker:
    def __init__(self, existing_profiles: list[dict], composite_keys: list[str], threshold: int = 6):
        self.existing = existing_profiles
        self.keys = composite_keys
        self.threshold = threshold

    def is_unique(self, candidate: dict) -> bool:
        for existing in self.existing:
            matches = sum(1 for k in self.keys if candidate.get(k) == existing.get(k))
            if matches >= self.threshold:
                return False
        return True

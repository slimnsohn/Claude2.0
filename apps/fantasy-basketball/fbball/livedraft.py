"""Live draft-day assistant engine — tracks the draft as it happens and
recommends the best available player, either by raw projected value or weighted
to your roster's category needs.

Pure state machine; the interactive CLI (livedraft.py) is a thin shell over it.
"""

import unicodedata
from difflib import get_close_matches

from fbball import recommend


def _norm(s: str) -> str:
    """Lowercase + strip accents so 'jokic' matches 'Jokić'."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().strip()


class LiveDraft:
    def __init__(self, ranked: list[dict]):
        # ranked: valued players (projection board), pre-sorted by total_value desc
        self.ranked = list(ranked)
        self.by_id = {p["player_id"]: p for p in self.ranked}
        self.drafted = set()
        self.mine = []        # my picks, in order
        self._history = []    # (player_id, mine_bool) for undo

    # ---- draft actions ----
    def draft(self, player_id, mine: bool = False) -> bool:
        if player_id in self.drafted:
            return False
        self.drafted.add(player_id)
        if mine:
            self.mine.append(player_id)
        self._history.append((player_id, mine))
        return True

    def undo(self):
        if not self._history:
            return None
        pid, mine = self._history.pop()
        self.drafted.discard(pid)
        if mine and self.mine and self.mine[-1] == pid:
            self.mine.pop()
        return pid

    # ---- views ----
    def available(self) -> list[dict]:
        return [p for p in self.ranked if p["player_id"] not in self.drafted]

    def best(self, n: int = 15) -> list[dict]:
        return self.available()[:n]

    def my_players(self) -> list[dict]:
        return [self.by_id[pid] for pid in self.mine]

    def by_need(self, n: int = 15) -> list[dict]:
        """Best available weighted by my roster's current category needs."""
        profile = recommend.category_profile(self.my_players())
        weights = recommend.needs_weights(profile)
        return recommend.rank_waivers(self.available(), weights)[:n]

    # ---- name resolution ----
    def resolve(self, name: str):
        """Find a player by (fuzzy) name; None if no confident match."""
        q = _norm(name)
        if not q:
            return None
        names = {_norm(p["full_name"]): p for p in self.ranked}
        if q in names:
            return names[q]
        # unique substring
        subs = [p for low, p in names.items() if q in low]
        if len(subs) == 1:
            return subs[0]
        match = get_close_matches(q, list(names.keys()), n=1, cutoff=0.6)
        return names[match[0]] if match else None

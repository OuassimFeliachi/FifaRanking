"""Abstract base class for rating engines."""

from abc import ABC, abstractmethod


class RatingEngine(ABC):
    """Base class all rating engines must implement."""

    name: str = "base"

    @abstractmethod
    def compute_snapshots(self, matches: list, players: list) -> list[dict]:
        """
        Compute rating changes for all matches in chronological order.

        Returns a list of snapshot dicts with keys:
          match_id, player_id, system_name, rating_before, rating_after,
          expected_score, actual_score, delta, rd_before, rd_after
        """
        ...

    @abstractmethod
    def final_ratings(self, matches: list, players: list) -> dict[int, float]:
        """Return {player_id: final_rating} after processing all matches."""
        ...

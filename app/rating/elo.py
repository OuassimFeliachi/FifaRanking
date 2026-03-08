"""Elo rating engine."""

from app.rating.base import RatingEngine

INITIAL_RATING = 1500.0
K_FACTOR = 32


def _expected(rating: float, opp: float) -> float:
    return 1.0 / (1.0 + 10 ** ((opp - rating) / 400.0))


def _actual(score1: int, score2: int) -> tuple[float, float]:
    if score1 > score2:
        return 1.0, 0.0
    elif score1 < score2:
        return 0.0, 1.0
    return 0.5, 0.5


class EloEngine(RatingEngine):
    name = "elo"

    def compute_snapshots(self, matches: list, players: list) -> list[dict]:
        ratings = {p.id: INITIAL_RATING for p in players}
        snapshots = []

        sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))

        for match in sorted_matches:
            r1 = ratings[match.player1_id]
            r2 = ratings[match.player2_id]

            e1 = _expected(r1, r2)
            e2 = _expected(r2, r1)
            a1, a2 = _actual(match.score1, match.score2)

            new_r1 = r1 + K_FACTOR * (a1 - e1)
            new_r2 = r2 + K_FACTOR * (a2 - e2)

            snapshots.append({
                "match_id": match.id,
                "player_id": match.player1_id,
                "system_name": "elo",
                "rating_before": r1,
                "rating_after": new_r1,
                "expected_score": round(e1, 4),
                "actual_score": a1,
                "delta": round(new_r1 - r1, 2),
                "rd_before": None,
                "rd_after": None,
            })
            snapshots.append({
                "match_id": match.id,
                "player_id": match.player2_id,
                "system_name": "elo",
                "rating_before": r2,
                "rating_after": new_r2,
                "expected_score": round(e2, 4),
                "actual_score": a2,
                "delta": round(new_r2 - r2, 2),
                "rd_before": None,
                "rd_after": None,
            })

            ratings[match.player1_id] = new_r1
            ratings[match.player2_id] = new_r2

        return snapshots

    def final_ratings(self, matches: list, players: list) -> dict[int, float]:
        ratings = {p.id: INITIAL_RATING for p in players}
        sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))
        for match in sorted_matches:
            r1, r2 = ratings[match.player1_id], ratings[match.player2_id]
            e1 = _expected(r1, r2)
            e2 = _expected(r2, r1)
            a1, a2 = _actual(match.score1, match.score2)
            ratings[match.player1_id] = r1 + K_FACTOR * (a1 - e1)
            ratings[match.player2_id] = r2 + K_FACTOR * (a2 - e2)
        return ratings

    def win_probability(self, rating1: float, rating2: float) -> float:
        """Expected win probability for player 1."""
        return _expected(rating1, rating2)

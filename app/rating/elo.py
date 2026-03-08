"""
Elo rating engine with:
- Provisional K (40 / 24 / 20 based on games played)
- Goal-difference multiplier (1.00 – 1.15)
- Same-day repeat-pair damping (1.00 / 0.75 / 0.50)
"""

from app.rating.base import RatingEngine

INITIAL_RATING = 1500.0


def _expected(rating: float, opp: float) -> float:
    return 1.0 / (1.0 + 10 ** ((opp - rating) / 400.0))


def _actual(score1: int, score2: int) -> tuple:
    if score1 > score2:
        return 1.0, 0.0
    elif score1 < score2:
        return 0.0, 1.0
    return 0.5, 0.5


def _base_k(games_played: int) -> float:
    """Provisional K factor based on games played before this match."""
    if games_played < 5:
        return 40.0
    elif games_played < 15:
        return 24.0
    return 20.0


def _goal_diff_mult(score1: int, score2: int) -> float:
    """Multiplier for goal difference. Bigger wins matter slightly more."""
    diff = abs(score1 - score2)
    if diff <= 1:
        return 1.00
    elif diff == 2:
        return 1.05
    elif diff == 3:
        return 1.10
    return 1.15  # 4+


class EloEngine(RatingEngine):
    name = "elo"

    def compute_snapshots(self, matches: list, players: list) -> list:
        ratings = {p.id: INITIAL_RATING for p in players}
        games_played = {p.id: 0 for p in players}
        snapshots = []

        sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))

        # Track daily pair encounter count for repeat damping.
        # key = (date, frozenset({p1_id, p2_id})), value = count so far
        daily_pair_count: dict = {}

        for match in sorted_matches:
            p1_id = match.player1_id
            p2_id = match.player2_id

            r1 = ratings[p1_id]
            r2 = ratings[p2_id]

            # ── Provisional K (average of both players' individual K) ──
            k1 = _base_k(games_played[p1_id])
            k2 = _base_k(games_played[p2_id])
            base_k = (k1 + k2) / 2.0

            # ── Goal-difference multiplier ──
            gd_mult = _goal_diff_mult(match.score1, match.score2)

            # ── Same-day repeat-pair damping ──
            pair_key = (match.match_date, frozenset({p1_id, p2_id}))
            pair_count = daily_pair_count.get(pair_key, 0)
            daily_pair_count[pair_key] = pair_count + 1

            if pair_count < 2:      # 1st or 2nd encounter that day → full value
                repeat_mult = 1.00
            elif pair_count == 2:   # 3rd → 75 %
                repeat_mult = 0.75
            else:                   # 4th+ → 50 %
                repeat_mult = 0.50

            # ── Effective K ──
            k_eff = base_k * gd_mult * repeat_mult

            e1 = _expected(r1, r2)
            e2 = _expected(r2, r1)
            a1, a2 = _actual(match.score1, match.score2)

            new_r1 = r1 + k_eff * (a1 - e1)
            new_r2 = r2 + k_eff * (a2 - e2)

            base_snap = {
                "system_name": "elo",
                "effective_k": round(k_eff, 2),
                "goal_diff_mult": gd_mult,
                "repeat_mult": repeat_mult,
                "rd_before": None,
                "rd_after": None,
            }

            snapshots.append({
                **base_snap,
                "match_id": match.id,
                "player_id": p1_id,
                "rating_before": r1,
                "rating_after": new_r1,
                "expected_score": round(e1, 4),
                "actual_score": a1,
                "delta": round(new_r1 - r1, 2),
            })
            snapshots.append({
                **base_snap,
                "match_id": match.id,
                "player_id": p2_id,
                "rating_before": r2,
                "rating_after": new_r2,
                "expected_score": round(e2, 4),
                "actual_score": a2,
                "delta": round(new_r2 - r2, 2),
            })

            ratings[p1_id] = new_r1
            ratings[p2_id] = new_r2
            games_played[p1_id] += 1
            games_played[p2_id] += 1

        return snapshots

    def final_ratings(self, matches: list, players: list) -> dict:
        snaps = self.compute_snapshots(matches, players)
        result = {p.id: INITIAL_RATING for p in players}
        for s in snaps:
            result[s["player_id"]] = s["rating_after"]
        return result

    def win_probability(self, rating1: float, rating2: float) -> float:
        """Expected win probability for player 1."""
        return _expected(rating1, rating2)

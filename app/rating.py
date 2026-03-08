"""
Elo rating computation module.

Ratings are recomputed from scratch each time match data changes,
processing matches in chronological order (then insertion order for ties).
"""

INITIAL_RATING = 1500.0
K_FACTOR = 32


def expected_score(rating: float, opponent_rating: float) -> float:
    """Compute expected score for a player against an opponent."""
    return 1.0 / (1.0 + 10 ** ((opponent_rating - rating) / 400.0))


def update_ratings(
    rating1: float, rating2: float, score1: int, score2: int
) -> tuple[float, float]:
    """
    Compute new Elo ratings after a match.

    Returns (new_rating1, new_rating2).
    Actual score: win=1, draw=0.5, loss=0.
    """
    if score1 > score2:
        actual1, actual2 = 1.0, 0.0
    elif score1 < score2:
        actual1, actual2 = 0.0, 1.0
    else:
        actual1, actual2 = 0.5, 0.5

    exp1 = expected_score(rating1, rating2)
    exp2 = expected_score(rating2, rating1)

    new_rating1 = rating1 + K_FACTOR * (actual1 - exp1)
    new_rating2 = rating2 + K_FACTOR * (actual2 - exp2)

    return new_rating1, new_rating2


def recompute_all_ratings(matches: list, players: list) -> dict[int, float]:
    """
    Recompute Elo ratings for all players from scratch.

    Args:
        matches: list of Match ORM objects, will be sorted by (match_date, id).
        players: list of Player ORM objects.

    Returns:
        dict mapping player_id -> current rating.
    """
    ratings = {p.id: INITIAL_RATING for p in players}

    # Sort matches chronologically, then by insertion order for same-date matches
    sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))

    for match in sorted_matches:
        r1 = ratings[match.player1_id]
        r2 = ratings[match.player2_id]
        new_r1, new_r2 = update_ratings(r1, r2, match.score1, match.score2)
        ratings[match.player1_id] = new_r1
        ratings[match.player2_id] = new_r2

    return ratings


def recompute_with_snapshots(matches: list, players: list) -> list[dict]:
    """
    Recompute ratings and return a list of snapshot dicts.

    Each dict contains: match_id, player_id, rating_before, rating_after.
    """
    ratings = {p.id: INITIAL_RATING for p in players}
    snapshots = []

    sorted_matches = sorted(matches, key=lambda m: (m.match_date, m.id))

    for match in sorted_matches:
        r1_before = ratings[match.player1_id]
        r2_before = ratings[match.player2_id]

        new_r1, new_r2 = update_ratings(r1_before, r2_before, match.score1, match.score2)

        snapshots.append(
            {
                "match_id": match.id,
                "player_id": match.player1_id,
                "rating_before": r1_before,
                "rating_after": new_r1,
            }
        )
        snapshots.append(
            {
                "match_id": match.id,
                "player_id": match.player2_id,
                "rating_before": r2_before,
                "rating_after": new_r2,
            }
        )

        ratings[match.player1_id] = new_r1
        ratings[match.player2_id] = new_r2

    return snapshots

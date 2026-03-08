"""
Business logic layer.

Keeps routes thin by centralising DB mutations and Elo recomputation.
"""

from datetime import date
from app import db
from app.models import Player, Match, RatingSnapshot
from app.rating import INITIAL_RATING, recompute_with_snapshots
from app.utils import normalize_name


# ---------------------------------------------------------------------------
# Player helpers
# ---------------------------------------------------------------------------

def get_or_create_player(name: str) -> Player:
    """Return existing player by normalized name, or create a new one."""
    norm = normalize_name(name)
    player = Player.query.filter_by(normalized_name=norm).first()
    if not player:
        player = Player(name=name.strip(), normalized_name=norm)
        db.session.add(player)
        db.session.flush()  # get player.id without full commit
    return player


def add_player(name: str) -> tuple[Player | None, str | None]:
    """
    Add a player. Returns (player, error_message).
    error_message is None on success.
    """
    norm = normalize_name(name)
    if not norm:
        return None, "Player name cannot be empty."
    existing = Player.query.filter_by(normalized_name=norm).first()
    if existing:
        return None, f"Player '{existing.name}' already exists."
    player = Player(name=name.strip(), normalized_name=norm)
    db.session.add(player)
    db.session.commit()
    return player, None


# ---------------------------------------------------------------------------
# Match helpers
# ---------------------------------------------------------------------------

def add_match(
    match_date: date,
    player1_id: int,
    player2_id: int,
    score1: int,
    score2: int,
) -> tuple[Match | None, str | None]:
    """
    Persist a match and recompute all ratings.
    Returns (match, error_message).
    """
    if player1_id == player2_id:
        return None, "A player cannot play against themselves."
    if score1 < 0 or score2 < 0:
        return None, "Scores must be >= 0."

    match = Match(
        match_date=match_date,
        player1_id=player1_id,
        player2_id=player2_id,
        score1=score1,
        score2=score2,
    )
    db.session.add(match)
    db.session.flush()  # get match.id

    _recompute_ratings()
    db.session.commit()
    return match, None


def _recompute_ratings():
    """Delete all snapshots and recompute from scratch."""
    RatingSnapshot.query.delete()

    all_matches = Match.query.all()
    all_players = Player.query.all()

    snapshots_data = recompute_with_snapshots(all_matches, all_players)

    for s in snapshots_data:
        db.session.add(RatingSnapshot(**s))


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def compute_player_stats(player: Player, current_rating: float) -> dict:
    """Compute win/draw/loss/goals stats for a player."""
    wins = draws = losses = goals_for = goals_against = 0

    for m in player.matches_as_p1:
        goals_for += m.score1
        goals_against += m.score2
        if m.score1 > m.score2:
            wins += 1
        elif m.score1 == m.score2:
            draws += 1
        else:
            losses += 1

    for m in player.matches_as_p2:
        goals_for += m.score2
        goals_against += m.score1
        if m.score2 > m.score1:
            wins += 1
        elif m.score2 == m.score1:
            draws += 1
        else:
            losses += 1

    games = wins + draws + losses
    win_rate = round(wins / games * 100, 1) if games else 0.0
    points = wins * 3 + draws

    return {
        "rating": round(current_rating, 1),
        "games": games,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_diff": goals_for - goals_against,
        "win_rate": win_rate,
        "points": points,
    }


def get_current_ratings() -> dict[int, float]:
    """
    Return {player_id: current_rating} from the latest snapshots.
    Falls back to INITIAL_RATING for players with no matches.
    """
    players = Player.query.all()
    ratings = {p.id: INITIAL_RATING for p in players}

    # Get the last snapshot per player (highest match_id processed)
    for player in players:
        last_snap = (
            RatingSnapshot.query
            .filter_by(player_id=player.id)
            .order_by(RatingSnapshot.id.desc())
            .first()
        )
        if last_snap:
            ratings[player.id] = last_snap.rating_after

    return ratings


def get_ranking() -> list[dict]:
    """
    Build the full ranking table sorted by Elo rating descending.
    """
    players = Player.query.all()
    ratings = get_current_ratings()

    rows = []
    for p in players:
        stats = compute_player_stats(p, ratings[p.id])
        stats["id"] = p.id
        stats["name"] = p.name
        rows.append(stats)

    rows.sort(key=lambda r: r["rating"], reverse=True)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    return rows


def get_player_rating_history(player: Player) -> list[dict]:
    """
    Return the rating evolution for a player as a list of
    {label, rating} dicts, starting from the initial rating.
    """
    snapshots = (
        RatingSnapshot.query
        .filter_by(player_id=player.id)
        .join(Match, RatingSnapshot.match_id == Match.id)
        .order_by(Match.match_date, Match.id)
        .all()
    )

    history = [{"label": "Start", "rating": INITIAL_RATING}]
    for snap in snapshots:
        match = snap.match
        opp_id = (
            match.player2_id if match.player1_id == player.id else match.player1_id
        )
        opp = Player.query.get(opp_id)
        label = f"{match.match_date} vs {opp.name}"
        history.append({"label": label, "rating": round(snap.rating_after, 1)})

    return history


def get_player_recent_matches(player: Player, limit: int = 10) -> list[Match]:
    """Return the most recent matches for a player."""
    from sqlalchemy import or_, desc
    return (
        Match.query
        .filter(
            or_(Match.player1_id == player.id, Match.player2_id == player.id)
        )
        .order_by(desc(Match.match_date), desc(Match.id))
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

def import_matches_from_csv(file_stream) -> tuple[int, list[str]]:
    """
    Parse a CSV file and import matches.

    Expected columns: Date,Joueur 1,Score J1,Score J2,Joueur 2
    Date format: dd/mm/yyyy

    Returns (count_imported, list_of_errors).
    """
    import csv
    from datetime import datetime

    errors = []
    count = 0

    # Auto-detect delimiter: sniff the first line for ; vs ,
    first_line = file_stream.readline().decode("utf-8")
    delimiter = ";" if ";" in first_line else ","
    remaining = file_stream.read()
    lines = iter((first_line + remaining.decode("utf-8")).splitlines(keepends=True))

    reader = csv.DictReader(lines, delimiter=delimiter, skipinitialspace=True)

    for line_num, row in enumerate(reader, start=2):
        try:
            date_str = row.get("Date", "").strip()
            name1 = row.get("Joueur 1", "").strip()
            name2 = row.get("Joueur 2", "").strip()
            score1_str = row.get("Score J1", "").strip()
            score2_str = row.get("Score J2", "").strip()

            if not all([date_str, name1, name2, score1_str, score2_str]):
                errors.append(f"Line {line_num}: missing field(s), skipped.")
                continue

            match_date = datetime.strptime(date_str, "%d/%m/%Y").date()
            score1 = int(score1_str)
            score2 = int(score2_str)

            p1 = get_or_create_player(name1)
            p2 = get_or_create_player(name2)

            if p1.id == p2.id:
                errors.append(f"Line {line_num}: same player on both sides, skipped.")
                continue

            match = Match(
                match_date=match_date,
                player1_id=p1.id,
                player2_id=p2.id,
                score1=score1,
                score2=score2,
            )
            db.session.add(match)
            count += 1

        except Exception as exc:
            errors.append(f"Line {line_num}: {exc}")

    if count:
        db.session.flush()
        _recompute_ratings()

    db.session.commit()
    return count, errors

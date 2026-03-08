"""
Business logic layer.

Keeps routes thin by centralising DB mutations and rating recomputation.
"""

import json
from datetime import date
from sqlalchemy import or_, desc

from app import db
from app.models import Player, Match, RatingSnapshot, AuditLog, AppSetting
from app.rating import INITIAL_RATING
from app.rating.engine import get_active_engine, get_engine
from app.utils import normalize_name


# ---------------------------------------------------------------------------
# AppSetting helpers
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    s = AppSetting.query.filter_by(key=key).first()
    return s.value if s else default


def set_setting(key: str, value: str):
    s = AppSetting.query.filter_by(key=key).first()
    if s:
        s.value = value
    else:
        s = AppSetting(key=key, value=value)
        db.session.add(s)
    db.session.commit()


def get_active_system() -> str:
    return get_setting("rating_system", "elo")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def audit_log(entity_type: str, entity_id: int, action: str,
              old=None, new=None, actor: str = "admin"):
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        old_data_json=json.dumps(old) if old is not None else None,
        new_data_json=json.dumps(new) if new is not None else None,
    )
    db.session.add(entry)


def _match_to_dict(m: Match) -> dict:
    return {
        "id": m.id,
        "match_date": str(m.match_date),
        "player1_id": m.player1_id,
        "player2_id": m.player2_id,
        "score1": m.score1,
        "score2": m.score2,
    }


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
        db.session.flush()
    return player


def add_player(name: str) -> tuple:
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
# Rating recomputation
# ---------------------------------------------------------------------------

def _recompute_ratings(system: str = None):
    """
    Delete all snapshots for the given system and recompute from scratch.
    Also updates Player.rating (for active system) and glicko columns.
    """
    if system is None:
        system = get_active_system()

    # Delete existing snapshots for this system
    RatingSnapshot.query.filter_by(system_name=system).delete()

    all_matches = Match.query.all()
    all_players = Player.query.all()

    engine = get_engine(system)
    snapshots_data = engine.compute_snapshots(all_matches, all_players)

    for s in snapshots_data:
        db.session.add(RatingSnapshot(**s))

    # Update Player columns
    if system == "elo":
        final = {}
        for s in snapshots_data:
            final[s["player_id"]] = s["rating_after"]
        for p in all_players:
            if p.id in final:
                p.rating = round(final[p.id], 2)
            else:
                p.rating = INITIAL_RATING

    elif system == "glicko2":
        from app.rating.glicko import Glicko2Engine, INITIAL_RD, INITIAL_VOL
        glicko_engine = Glicko2Engine()
        state = glicko_engine.final_state(all_matches, all_players)
        for p in all_players:
            if p.id in state:
                p.glicko_rating = round(state[p.id]["r"], 2)
                p.glicko_rd = round(state[p.id]["rd"], 2)
                p.glicko_vol = state[p.id]["vol"]
            else:
                p.glicko_rating = INITIAL_R_GLICKO
                p.glicko_rd = INITIAL_RD
                p.glicko_vol = INITIAL_VOL


def recompute_all_ratings(system: str = None):
    """Public wrapper: recompute, flush, commit."""
    if system is None:
        system = get_active_system()
    _recompute_ratings(system)
    db.session.commit()


# ---------------------------------------------------------------------------
# Match helpers
# ---------------------------------------------------------------------------

def add_match(
    match_date: date,
    player1_id: int,
    player2_id: int,
    score1: int,
    score2: int,
) -> tuple:
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
    db.session.flush()

    new_data = _match_to_dict(match)
    audit_log("match", match.id, "create", old=None, new=new_data)

    _recompute_ratings()
    db.session.commit()
    return match, None


def edit_match(
    match_id: int,
    match_date: date,
    player1_id: int,
    player2_id: int,
    score1: int,
    score2: int,
) -> tuple:
    """
    Edit an existing match and recompute all ratings.
    Returns (match, error_message).
    """
    match = Match.query.get(match_id)
    if not match:
        return None, "Match not found."
    if player1_id == player2_id:
        return None, "A player cannot play against themselves."
    if score1 < 0 or score2 < 0:
        return None, "Scores must be >= 0."

    old_data = _match_to_dict(match)

    match.match_date = match_date
    match.player1_id = player1_id
    match.player2_id = player2_id
    match.score1 = score1
    match.score2 = score2

    new_data = _match_to_dict(match)
    audit_log("match", match.id, "edit", old=old_data, new=new_data)

    _recompute_ratings()
    db.session.commit()
    return match, None


def delete_match(match_id: int) -> tuple:
    """
    Delete a match and recompute all ratings.
    Returns (True, None) on success or (False, error_message).
    """
    match = Match.query.get(match_id)
    if not match:
        return False, "Match not found."

    old_data = _match_to_dict(match)

    # Delete snapshots first
    RatingSnapshot.query.filter_by(match_id=match_id).delete()
    db.session.delete(match)
    db.session.flush()

    audit_log("match", match_id, "delete", old=old_data, new=None)

    _recompute_ratings()
    db.session.commit()
    return True, None


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


def get_current_ratings(system: str = None) -> dict:
    """
    Return {player_id: current_rating} from the latest snapshots.
    Falls back to INITIAL_RATING for players with no matches.
    """
    if system is None:
        system = get_active_system()

    players = Player.query.all()
    ratings = {p.id: INITIAL_RATING for p in players}

    for player in players:
        last_snap = (
            RatingSnapshot.query
            .filter_by(player_id=player.id, system_name=system)
            .order_by(RatingSnapshot.id.desc())
            .first()
        )
        if last_snap:
            ratings[player.id] = last_snap.rating_after

    return ratings


def _get_previous_rankings(system: str) -> dict:
    """
    Return {player_id: rank} from the second-to-last batch of snapshots.
    Used for movement indicators.
    """
    # Find the latest match_id that has snapshots
    latest_snap = (
        RatingSnapshot.query
        .filter_by(system_name=system)
        .order_by(RatingSnapshot.id.desc())
        .first()
    )
    if not latest_snap:
        return {}

    latest_match_id = latest_snap.match_id

    # Find the previous match_id
    prev_snap = (
        RatingSnapshot.query
        .filter(
            RatingSnapshot.system_name == system,
            RatingSnapshot.match_id < latest_match_id,
        )
        .order_by(RatingSnapshot.match_id.desc())
        .first()
    )
    if not prev_snap:
        return {}

    prev_match_id = prev_snap.match_id

    # Get ratings at that point in time (last snapshot with match_id <= prev_match_id)
    players = Player.query.all()
    prev_ratings = {}
    for p in players:
        snap = (
            RatingSnapshot.query
            .filter(
                RatingSnapshot.player_id == p.id,
                RatingSnapshot.system_name == system,
                RatingSnapshot.match_id <= prev_match_id,
            )
            .order_by(RatingSnapshot.id.desc())
            .first()
        )
        if snap:
            prev_ratings[p.id] = snap.rating_after
        else:
            prev_ratings[p.id] = INITIAL_RATING

    # Rank them
    sorted_players = sorted(prev_ratings.items(), key=lambda x: x[1], reverse=True)
    return {pid: rank + 1 for rank, (pid, _) in enumerate(sorted_players)}


def get_ranking(system: str = None) -> list:
    """
    Build the full ranking table sorted by rating descending.
    Includes rank movement vs previous snapshot batch.
    """
    if system is None:
        system = get_active_system()

    players = Player.query.all()
    ratings = get_current_ratings(system)
    prev_ranks = _get_previous_rankings(system)

    rows = []
    for p in players:
        stats = compute_player_stats(p, ratings[p.id])
        stats["id"] = p.id
        stats["name"] = p.name
        if system == "glicko2":
            stats["rd"] = round(p.glicko_rd or 350.0, 1)
        rows.append(stats)

    rows.sort(key=lambda r: r["rating"], reverse=True)

    for i, row in enumerate(rows, start=1):
        row["rank"] = i
        prev = prev_ranks.get(row["id"])
        if prev is None:
            row["movement"] = None
            row["movement_dir"] = "new"
        else:
            diff = prev - i
            row["movement"] = abs(diff) if diff != 0 else None
            row["movement_dir"] = "up" if diff > 0 else ("down" if diff < 0 else "same")

    return rows


def get_player_rating_history(player: Player, system: str = None) -> list:
    """
    Return the rating evolution for a player as a list of
    {label, rating} dicts, starting from the initial rating.
    """
    if system is None:
        system = get_active_system()

    snapshots = (
        RatingSnapshot.query
        .filter_by(player_id=player.id, system_name=system)
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


def get_player_recent_matches(player: Player, limit: int = 10) -> list:
    """Return the most recent matches for a player."""
    return (
        Match.query
        .filter(
            or_(Match.player1_id == player.id, Match.player2_id == player.id)
        )
        .order_by(desc(Match.match_date), desc(Match.id))
        .limit(limit)
        .all()
    )


def _get_form(player: Player, n: int = 5) -> list:
    """Return last N results as list of 'W'/'D'/'L' strings (most recent first)."""
    matches = get_player_recent_matches(player, limit=n)
    form = []
    for m in matches:
        is_p1 = m.player1_id == player.id
        my = m.score1 if is_p1 else m.score2
        opp = m.score2 if is_p1 else m.score1
        if my > opp:
            form.append("W")
        elif my == opp:
            form.append("D")
        else:
            form.append("L")
    return form


def _get_streaks(player: Player) -> dict:
    """Compute current streak, longest win streak, longest loss streak."""
    all_matches = (
        Match.query
        .filter(or_(Match.player1_id == player.id, Match.player2_id == player.id))
        .order_by(Match.match_date, Match.id)
        .all()
    )

    results = []
    for m in all_matches:
        is_p1 = m.player1_id == player.id
        my = m.score1 if is_p1 else m.score2
        opp = m.score2 if is_p1 else m.score1
        if my > opp:
            results.append("W")
        elif my == opp:
            results.append("D")
        else:
            results.append("L")

    if not results:
        return {"current": 0, "current_type": None, "longest_win": 0, "longest_loss": 0}

    # Current streak
    current_type = results[-1]
    current = 0
    for r in reversed(results):
        if r == current_type:
            current += 1
        else:
            break

    # Longest win streak
    longest_win = cur_win = 0
    for r in results:
        if r == "W":
            cur_win += 1
            longest_win = max(longest_win, cur_win)
        else:
            cur_win = 0

    # Longest loss streak
    longest_loss = cur_loss = 0
    for r in results:
        if r == "L":
            cur_loss += 1
            longest_loss = max(longest_loss, cur_loss)
        else:
            cur_loss = 0

    return {
        "current": current,
        "current_type": current_type,
        "longest_win": longest_win,
        "longest_loss": longest_loss,
    }


def get_head_to_head(p1_id: int, p2_id: int) -> dict:
    """Return H2H stats between two players."""
    matches = (
        Match.query
        .filter(
            or_(
                (Match.player1_id == p1_id) & (Match.player2_id == p2_id),
                (Match.player1_id == p2_id) & (Match.player2_id == p1_id),
            )
        )
        .order_by(Match.match_date, Match.id)
        .all()
    )

    p1_wins = p2_wins = draws = 0
    p1_goals = p2_goals = 0

    for m in matches:
        if m.player1_id == p1_id:
            s1, s2 = m.score1, m.score2
        else:
            s1, s2 = m.score2, m.score1

        p1_goals += s1
        p2_goals += s2

        if s1 > s2:
            p1_wins += 1
        elif s2 > s1:
            p2_wins += 1
        else:
            draws += 1

    return {
        "total": len(matches),
        "p1_wins": p1_wins,
        "p2_wins": p2_wins,
        "draws": draws,
        "p1_goals": p1_goals,
        "p2_goals": p2_goals,
        "matches": matches,
    }


def get_player_stats_rich(player_id: int, system: str = None) -> dict:
    """
    Rich stats for player detail page: form, streaks, h2h with all opponents.
    """
    if system is None:
        system = get_active_system()

    player = Player.query.get(player_id)
    if not player:
        return {}

    ratings = get_current_ratings(system)
    stats = compute_player_stats(player, ratings.get(player.id, INITIAL_RATING))
    rating_history = get_player_rating_history(player, system)
    recent_matches = get_player_recent_matches(player, limit=10)
    form = _get_form(player, n=5)
    streaks = _get_streaks(player)

    # H2H vs all opponents
    opponents = Player.query.filter(Player.id != player.id).all()
    h2h_list = []
    for opp in opponents:
        h = get_head_to_head(player.id, opp.id)
        if h["total"] > 0:
            h["opponent"] = opp
            h2h_list.append(h)
    h2h_list.sort(key=lambda x: x["total"], reverse=True)

    return {
        "player": player,
        "stats": stats,
        "rating_history": rating_history,
        "recent_matches": recent_matches,
        "form": form,
        "streaks": streaks,
        "h2h_list": h2h_list,
        "system": system,
    }


def predict_match(p1_id: int, p2_id: int, system: str = None) -> dict:
    """
    Predict win/draw/loss probabilities for a match between two players.
    """
    if system is None:
        system = get_active_system()

    p1 = Player.query.get(p1_id)
    p2 = Player.query.get(p2_id)
    if not p1 or not p2:
        return {}

    if system == "glicko2":
        from app.rating.glicko import Glicko2Engine
        engine = Glicko2Engine()
        r1 = p1.glicko_rating or 1500.0
        rd1 = p1.glicko_rd or 350.0
        r2 = p2.glicko_rating or 1500.0
        rd2 = p2.glicko_rd or 350.0
        win1 = engine.win_probability(r1, rd1, r2, rd2)
        win2 = engine.win_probability(r2, rd2, r1, rd1)
        diff = abs(r1 - r2)
    else:
        from app.rating.elo import EloEngine
        engine = EloEngine()
        ratings = get_current_ratings(system)
        r1 = ratings.get(p1_id, 1500.0)
        r2 = ratings.get(p2_id, 1500.0)
        win1 = engine.win_probability(r1, r2)
        win2 = engine.win_probability(r2, r1)
        diff = abs(r1 - r2)

    # Draw probability model: higher when ratings are close
    base_draw = 0.25
    draw_prob = base_draw * max(0.0, 1.0 - diff / 800.0)

    # Normalize win probabilities after accounting for draw
    remaining = 1.0 - draw_prob
    total_win = win1 + win2
    if total_win > 0:
        p1_win = remaining * win1 / total_win
        p2_win = remaining * win2 / total_win
    else:
        p1_win = p2_win = remaining / 2.0

    h2h = get_head_to_head(p1_id, p2_id)

    return {
        "p1": p1,
        "p2": p2,
        "p1_win": round(p1_win * 100, 1),
        "draw": round(draw_prob * 100, 1),
        "p2_win": round(p2_win * 100, 1),
        "r1": round(r1, 1),
        "r2": round(r2, 1),
        "diff": round(diff, 1),
        "h2h": h2h,
        "system": system,
    }


def get_fun_stats() -> dict:
    """Return fun / record stats."""
    matches = Match.query.order_by(Match.match_date, Match.id).all()
    players = Player.query.all()

    if not matches:
        return {}

    # Biggest win margin
    biggest_margin = None
    for m in matches:
        margin = abs(m.score1 - m.score2)
        if biggest_margin is None or margin > biggest_margin["margin"]:
            winner = m.player1 if m.score1 > m.score2 else m.player2
            loser = m.player2 if m.score1 > m.score2 else m.player1
            biggest_margin = {
                "match": m,
                "margin": margin,
                "winner": winner,
                "loser": loser,
            }

    # Highest scoring match
    most_goals = None
    for m in matches:
        total = m.score1 + m.score2
        if most_goals is None or total > most_goals["total"]:
            most_goals = {"match": m, "total": total}

    # Most games played
    game_counts = {}
    for p in players:
        cnt = p.matches_as_p1.count() + p.matches_as_p2.count()
        game_counts[p.id] = (p, cnt)
    most_games_player = max(game_counts.values(), key=lambda x: x[1], default=(None, 0))

    # Best win rate (min 3 games)
    best_winrate = None
    for p in players:
        wins = draws = losses = 0
        for m in p.matches_as_p1:
            if m.score1 > m.score2: wins += 1
            elif m.score1 == m.score2: draws += 1
            else: losses += 1
        for m in p.matches_as_p2:
            if m.score2 > m.score1: wins += 1
            elif m.score2 == m.score1: draws += 1
            else: losses += 1
        games = wins + draws + losses
        if games >= 3:
            wr = wins / games * 100
            if best_winrate is None or wr > best_winrate["rate"]:
                best_winrate = {"player": p, "rate": round(wr, 1), "games": games}

    # Highest scorer
    goal_counts = {}
    for p in players:
        gf = sum(m.score1 for m in p.matches_as_p1) + sum(m.score2 for m in p.matches_as_p2)
        goal_counts[p.id] = (p, gf)
    top_scorer = max(goal_counts.values(), key=lambda x: x[1], default=(None, 0))

    # Longest win streak across all players
    longest_streak = None
    for p in players:
        s = _get_streaks(p)
        if longest_streak is None or s["longest_win"] > longest_streak["streak"]:
            longest_streak = {"player": p, "streak": s["longest_win"]}

    # Most draws
    draw_counts = {}
    for p in players:
        d = sum(1 for m in p.matches_as_p1 if m.score1 == m.score2)
        d += sum(1 for m in p.matches_as_p2 if m.score1 == m.score2)
        draw_counts[p.id] = (p, d)
    most_draws = max(draw_counts.values(), key=lambda x: x[1], default=(None, 0))

    return {
        "total_matches": len(matches),
        "total_players": len(players),
        "biggest_margin": biggest_margin,
        "most_goals": most_goals,
        "most_games": most_games_player,
        "best_winrate": best_winrate,
        "top_scorer": top_scorer,
        "longest_streak": longest_streak,
        "most_draws": most_draws,
    }


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

def import_matches_from_csv(file_stream) -> tuple:
    """
    Parse a CSV file and import matches.

    Expected columns: Date,Joueur 1,Score J1,Score J2,Joueur 2
    Date format: dd/mm/yyyy

    Returns (count_imported, list_of_errors).
    """
    import csv
    from datetime import datetime as dt

    errors = []
    count = 0

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

            match_date = dt.strptime(date_str, "%d/%m/%Y").date()
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


# ---------------------------------------------------------------------------
# Backwards-compat alias used by old rating.py snapshot format
# ---------------------------------------------------------------------------

INITIAL_R_GLICKO = 1500.0

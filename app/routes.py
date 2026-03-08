from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import Player, Match, AuditLog, AppSetting
from app import db
import app.services as svc

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------------------
# Ranking (home)
# ---------------------------------------------------------------------------

@bp.route("/")
def index():
    system = svc.get_active_system()
    ranking = svc.get_ranking(system)

    # Ranking filters (applied after DB query since player count is small)
    name_filter = request.args.get("name", "").strip().lower()
    min_games = request.args.get("min_games", 0, type=int)

    if name_filter:
        ranking = [r for r in ranking if name_filter in r["name"].lower()]
    if min_games > 0:
        ranking = [r for r in ranking if r["games"] >= min_games]

    all_players = Player.query.order_by(Player.name).all()
    return render_template(
        "index.html",
        ranking=ranking,
        system=system,
        all_players=all_players,
        name_filter=name_filter,
        min_games=min_games,
    )


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@bp.route("/players", methods=["GET", "POST"])
def players():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        _, error = svc.add_player(name)
        if not error:
            flash(f"Player '{name}' added.", "success")
            return redirect(url_for("main.players"))

    all_players = Player.query.order_by(Player.name).all()
    return render_template("players.html", players=all_players, error=error)


# ---------------------------------------------------------------------------
# Player detail
# ---------------------------------------------------------------------------

@bp.route("/players/<int:player_id>")
def player_detail(player_id):
    player = Player.query.get_or_404(player_id)
    system = svc.get_active_system()
    rich = svc.get_player_stats_rich(player_id, system)
    all_players = Player.query.filter(Player.id != player_id).order_by(Player.name).all()
    return render_template(
        "player_detail.html",
        player=player,
        stats=rich["stats"],
        recent_matches=rich["recent_matches"],
        snapshots_by_match=rich["snapshots_by_match"],
        rating_history=rich["rating_history"],
        form=rich["form"],
        streaks=rich["streaks"],
        h2h_list=rich["h2h_list"],
        system=system,
        all_players=all_players,
    )


# ---------------------------------------------------------------------------
# Add match
# ---------------------------------------------------------------------------

@bp.route("/add-match", methods=["GET", "POST"])
def add_match():
    error = None
    all_players = Player.query.order_by(Player.name).all()

    if request.method == "POST":
        try:
            match_date = date.fromisoformat(request.form["match_date"])
            player1_id = int(request.form["player1_id"])
            player2_id = int(request.form["player2_id"])
            score1 = int(request.form["score1"])
            score2 = int(request.form["score2"])
        except (KeyError, ValueError):
            error = "Invalid form data. Please check all fields."
        else:
            _, error = svc.add_match(match_date, player1_id, player2_id, score1, score2)
            if not error:
                flash("Match recorded successfully.", "success")
                return redirect(url_for("main.index"))

    return render_template(
        "add_match.html",
        players=all_players,
        error=error,
        today=date.today().isoformat(),
    )


# ---------------------------------------------------------------------------
# Edit match
# ---------------------------------------------------------------------------

@bp.route("/matches/<int:match_id>/edit", methods=["GET", "POST"])
def edit_match(match_id):
    match = Match.query.get_or_404(match_id)
    all_players = Player.query.order_by(Player.name).all()
    error = None

    if request.method == "POST":
        try:
            match_date = date.fromisoformat(request.form["match_date"])
            player1_id = int(request.form["player1_id"])
            player2_id = int(request.form["player2_id"])
            score1 = int(request.form["score1"])
            score2 = int(request.form["score2"])
        except (KeyError, ValueError):
            error = "Invalid form data. Please check all fields."
        else:
            _, error = svc.edit_match(match_id, match_date, player1_id, player2_id, score1, score2)
            if not error:
                flash("Match updated successfully.", "success")
                return redirect(url_for("main.matches"))

    return render_template(
        "edit_match.html",
        match=match,
        players=all_players,
        error=error,
    )


# ---------------------------------------------------------------------------
# Delete match
# ---------------------------------------------------------------------------

@bp.route("/matches/<int:match_id>/delete", methods=["POST"])
def delete_match(match_id):
    ok, error = svc.delete_match(match_id)
    if ok:
        flash("Match deleted.", "success")
    else:
        flash(f"Error: {error}", "danger")
    return redirect(url_for("main.matches"))


# ---------------------------------------------------------------------------
# Match history
# ---------------------------------------------------------------------------

@bp.route("/matches")
def matches():
    from sqlalchemy import or_, and_
    player_filter = request.args.get("player_id", type=int)
    opponent_filter = request.args.get("opponent_id", type=int)
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = Match.query

    if player_filter and opponent_filter:
        # Matches between this specific pair
        query = query.filter(
            or_(
                and_(Match.player1_id == player_filter, Match.player2_id == opponent_filter),
                and_(Match.player1_id == opponent_filter, Match.player2_id == player_filter),
            )
        )
    elif player_filter:
        query = query.filter(
            or_(Match.player1_id == player_filter, Match.player2_id == player_filter)
        )
    elif opponent_filter:
        query = query.filter(
            or_(Match.player1_id == opponent_filter, Match.player2_id == opponent_filter)
        )

    if date_from:
        try:
            query = query.filter(Match.match_date >= date.fromisoformat(date_from))
        except ValueError:
            pass

    if date_to:
        try:
            query = query.filter(Match.match_date <= date.fromisoformat(date_to))
        except ValueError:
            pass

    all_matches = query.order_by(Match.match_date.desc(), Match.id.desc()).all()
    all_players = Player.query.order_by(Player.name).all()

    return render_template(
        "matches.html",
        matches=all_matches,
        all_players=all_players,
        player_filter=player_filter,
        opponent_filter=opponent_filter,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

@bp.route("/import", methods=["GET", "POST"])
def import_csv():
    result = None
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename.endswith(".csv"):
            flash("Please upload a valid .csv file.", "danger")
        else:
            count, errors = svc.import_matches_from_csv(file.stream)
            result = {"count": count, "errors": errors}
            if count:
                flash(f"Imported {count} match(es) successfully.", "success")

    return render_template("import_csv.html", result=result)


# ---------------------------------------------------------------------------
# Records / fun stats
# ---------------------------------------------------------------------------

@bp.route("/records")
def records():
    stats = svc.get_fun_stats()
    return render_template("records.html", stats=stats)


# ---------------------------------------------------------------------------
# Predict match
# ---------------------------------------------------------------------------

@bp.route("/predict")
def predict():
    all_players = Player.query.order_by(Player.name).all()
    prediction = None
    p1_id = request.args.get("p1_id", type=int)
    p2_id = request.args.get("p2_id", type=int)
    system = svc.get_active_system()

    if p1_id and p2_id and p1_id != p2_id:
        prediction = svc.predict_match(p1_id, p2_id, system)

    return render_template(
        "predict.html",
        all_players=all_players,
        prediction=prediction,
        p1_id=p1_id,
        p2_id=p2_id,
        system=system,
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@bp.route("/audit")
def audit():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    logs = (
        AuditLog.query
        .order_by(AuditLog.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return render_template("audit.html", logs=logs)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        rating_system = request.form.get("rating_system", "elo")
        if rating_system not in ("elo", "glicko2"):
            flash("Invalid rating system.", "danger")
        else:
            old = svc.get_setting("rating_system", "elo")
            svc.set_setting("rating_system", rating_system)
            if old != rating_system:
                svc.recompute_all_ratings(rating_system)
                svc.audit_log("setting", None, "change_rating_system",
                              old={"rating_system": old},
                              new={"rating_system": rating_system})
                db.session.commit()
            flash(f"Rating system set to {rating_system}.", "success")
        return redirect(url_for("main.settings"))

    current_system = svc.get_active_system()
    return render_template("settings.html", current_system=current_system)


# ---------------------------------------------------------------------------
# How it works / Elo explained
# ---------------------------------------------------------------------------

@bp.route("/how-it-works")
def how_it_works():
    system = svc.get_active_system()
    return render_template("how_it_works.html", system=system)

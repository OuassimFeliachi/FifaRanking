from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import Player, Match
from app import db
import app.services as svc

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------------------
# Ranking (home)
# ---------------------------------------------------------------------------

@bp.route("/")
def index():
    ranking = svc.get_ranking()
    return render_template("index.html", ranking=ranking)


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
    ratings = svc.get_current_ratings()
    stats = svc.compute_player_stats(player, ratings[player.id])
    recent_matches = svc.get_player_recent_matches(player)
    rating_history = svc.get_player_rating_history(player)
    return render_template(
        "player_detail.html",
        player=player,
        stats=stats,
        recent_matches=recent_matches,
        rating_history=rating_history,
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
# Match history
# ---------------------------------------------------------------------------

@bp.route("/matches")
def matches():
    all_matches = (
        Match.query.order_by(Match.match_date, Match.id).all()
    )
    return render_template("matches.html", matches=all_matches)


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

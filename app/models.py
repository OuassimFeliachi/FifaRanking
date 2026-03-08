from app import db
from datetime import datetime


class Player(db.Model):
    __tablename__ = "player"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    normalized_name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    matches_as_p1 = db.relationship(
        "Match", foreign_keys="Match.player1_id", backref="player1", lazy="dynamic"
    )
    matches_as_p2 = db.relationship(
        "Match", foreign_keys="Match.player2_id", backref="player2", lazy="dynamic"
    )
    rating_snapshots = db.relationship(
        "RatingSnapshot", backref="player", lazy="dynamic"
    )

    def __repr__(self):
        return f"<Player {self.name}>"


class Match(db.Model):
    __tablename__ = "match"

    id = db.Column(db.Integer, primary_key=True)
    match_date = db.Column(db.Date, nullable=False)
    player1_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    score1 = db.Column(db.Integer, nullable=False)
    score2 = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    snapshots = db.relationship("RatingSnapshot", backref="match", lazy="dynamic")

    def __repr__(self):
        return f"<Match {self.player1_id} vs {self.player2_id} on {self.match_date}>"


class RatingSnapshot(db.Model):
    __tablename__ = "rating_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    rating_before = db.Column(db.Float, nullable=False)
    rating_after = db.Column(db.Float, nullable=False)

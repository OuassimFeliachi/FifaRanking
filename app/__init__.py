from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()


def _migrate_db(app):
    """
    Lightweight migration: add missing columns to existing tables via raw SQL.
    Safe to call every startup — each ALTER is only run if the column is absent.
    """
    import sqlite3

    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return  # brand-new DB — create_all will handle everything

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    def _col_exists(table, col):
        cur.execute(f"PRAGMA table_info({table})")
        return any(row[1] == col for row in cur.fetchall())

    def _add_col(table, col, typedef):
        if not _col_exists(table, col):
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

    # Player new columns
    _add_col("player", "rating",        "FLOAT DEFAULT 1500.0")
    _add_col("player", "glicko_rating", "FLOAT DEFAULT 1500.0")
    _add_col("player", "glicko_rd",     "FLOAT DEFAULT 350.0")
    _add_col("player", "glicko_vol",    "FLOAT DEFAULT 0.06")

    # RatingSnapshot new columns
    _add_col("rating_snapshot", "system_name",     "VARCHAR(20) DEFAULT 'elo'")
    _add_col("rating_snapshot", "expected_score",  "FLOAT")
    _add_col("rating_snapshot", "actual_score",    "FLOAT")
    _add_col("rating_snapshot", "delta",           "FLOAT")
    _add_col("rating_snapshot", "rd_before",       "FLOAT")
    _add_col("rating_snapshot", "rd_after",        "FLOAT")
    _add_col("rating_snapshot", "created_at",      "DATETIME")

    # Fix existing snapshots that have NULL system_name (from before this migration)
    cur.execute("UPDATE rating_snapshot SET system_name='elo' WHERE system_name IS NULL")

    conn.commit()
    conn.close()


def create_app():
    app = Flask(__name__)

    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{os.path.join(base_dir, 'elo.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "change-me-in-production"

    db.init_app(app)

    from app.routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        _migrate_db(app)  # add missing columns before create_all
        db.create_all()   # create any brand-new tables

    return app

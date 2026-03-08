"""
Active rating engine selector.

Reads the 'rating_system' key from AppSetting.
Defaults to 'elo' if not set.
"""

from app.rating.elo import EloEngine
from app.rating.glicko import Glicko2Engine

_ENGINES = {
    "elo": EloEngine,
    "glicko2": Glicko2Engine,
}


def get_active_engine():
    """
    Return an instance of the currently configured rating engine.
    Reads AppSetting(key='rating_system') from the DB; falls back to Elo.
    Must be called within an app context.
    """
    try:
        from app.models import AppSetting
        setting = AppSetting.query.filter_by(key="rating_system").first()
        system = setting.value if setting else "elo"
    except Exception:
        system = "elo"

    cls = _ENGINES.get(system, EloEngine)
    return cls()


def get_engine(name: str = "elo"):
    """Return an engine instance by name."""
    cls = _ENGINES.get(name, EloEngine)
    return cls()

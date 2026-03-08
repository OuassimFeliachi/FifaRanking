"""
Rating package.

Exports the engine factory and keeps backwards-compat constants
so that old imports like `from app.rating import INITIAL_RATING`
continue to work.
"""

from app.rating.engine import get_engine, get_active_engine
from app.rating.elo import INITIAL_RATING

# K_FACTOR is now dynamic (provisional K) — kept as alias for backwards compat
K_FACTOR = 20  # stable K value (used for reference only)

__all__ = [
    "get_engine",
    "get_active_engine",
    "INITIAL_RATING",
    "K_FACTOR",
]

"""
Backwards-compatibility shim.

This module used to contain the Elo logic directly.
All logic has been moved to the app/rating/ package.
Imports from here will still work for legacy code.
"""

# Re-export everything that was previously defined here
from app.rating.elo import (  # noqa: F401
    INITIAL_RATING,
    K_FACTOR,
    EloEngine,
)
from app.rating.engine import get_engine, get_active_engine  # noqa: F401


def recompute_all_ratings(matches, players):
    """Legacy wrapper — delegates to EloEngine."""
    from app.rating.elo import EloEngine
    return EloEngine().final_ratings(matches, players)


def recompute_with_snapshots(matches, players):
    """Legacy wrapper — delegates to EloEngine."""
    from app.rating.elo import EloEngine
    return EloEngine().compute_snapshots(matches, players)

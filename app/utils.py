"""Utility helpers."""

import unicodedata


def normalize_name(name: str) -> str:
    """
    Normalize a player name for deduplication.

    - Strip surrounding whitespace
    - Lowercase
    - Remove accents (NFD decomposition, keep only ASCII)

    Example: "Loïc" -> "loic"
    """
    name = name.strip()
    # Decompose characters into base + combining marks, then drop combining marks
    nfd = unicodedata.normalize("NFD", name)
    ascii_only = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return ascii_only.lower()

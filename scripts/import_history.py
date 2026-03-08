#!/usr/bin/env python
"""
CLI script to import match history from a CSV file.

Usage:
    python scripts/import_history.py path/to/matches.csv

Expected CSV columns:
    Date,Joueur 1,Score J1,Score J2,Joueur 2

Date format: dd/mm/yyyy
"""

import sys
import os

# Ensure the project root is in the path so we can import the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.services import import_matches_from_csv


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_history.py <csv_file>")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        sys.exit(1)

    app = create_app()
    with app.app_context():
        with open(csv_path, "rb") as f:
            count, errors = import_matches_from_csv(f)

    print(f"Imported {count} match(es).")
    if errors:
        print(f"{len(errors)} error(s):")
        for err in errors:
            print(f"  {err}")


if __name__ == "__main__":
    main()

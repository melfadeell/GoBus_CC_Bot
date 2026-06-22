"""Regenerate upcoming trips so today falls inside the trip window.

Run this on any machine where trip queries return nothing because the
originally seeded 14-day window has expired (all trips are in the past).

Usage (from the backend/ directory):
    venv/Scripts/python.exe -m scripts.reseed_trips           # 14 days
    venv/Scripts/python.exe -m scripts.reseed_trips --days 30 # custom window
"""

import argparse
from datetime import date

from app.database import SessionLocal
from app.seed.seed_demo_data import regenerate_all_trips


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate upcoming GoBus trips from today.")
    parser.add_argument("--days", type=int, default=14, help="Number of days to seed (default: 14)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        created = regenerate_all_trips(db, days=args.days)
    finally:
        db.close()

    print(f"Regenerated {created} trips starting from {date.today()} for {args.days} days.")


if __name__ == "__main__":
    main()

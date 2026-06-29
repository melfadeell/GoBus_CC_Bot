"""Behavioral regression suite for the GoBus bot tool executors.

Runs DIRECTLY against the chat_tools executors (no HTTP, no OpenAI cost) — the
deterministic layer the LLM's tool calls resolve to. Each scenario asserts the
structured behavior the executors guarantee: trip route resolution, price
ordering, "latest" direction, explicit counts, follow-up route memory (from
conversation history), station/destination cards, KB labels, and the no-data
fallback hint.

Tool *selection* itself is now the LLM's job (function calling) and needs a live
model, so it is intentionally out of scope here.

Usage (from backend/):  venv/Scripts/python.exe -m scripts.test_demo_scenarios
"""

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.services.chat_tools import (
    execute_find_station,
    execute_list_destinations,
    execute_search_kb,
    execute_search_trips,
)
from app.services.kb_retrieval import _HISTORY_SEP

NO_TRIP_HINT = "no matching upcoming trips"


@dataclass
class Trips:
    """A search_trips scenario."""

    name: str
    destination: str | None = None
    origin: str | None = None
    sort: str = "soonest"
    limit: int | None = None
    history: list[str] = field(default_factory=list)
    min_rows: int | None = None
    max_rows: int | None = None
    price_order: str | None = None          # 'asc' | 'desc'
    latest: bool = False                     # last row holds the max date
    contains: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)


@dataclass
class Station:
    name: str
    query: str
    expect_card: bool = True


@dataclass
class Dests:
    name: str


@dataclass
class Kb:
    name: str
    query: str
    topics: list[str] = field(default_factory=list)
    require: list[str] = field(default_factory=list)   # labels that must appear


def _meta_value(metas: list[dict], key: str):
    for m in metas:
        if key in m:
            return m[key]
    return None


def check_trips(db, s: Trips) -> list[str]:
    history_text = _HISTORY_SEP.join(s.history) if s.history else None
    text, metas = execute_search_trips(
        db,
        destination_city=s.destination,
        origin_city=s.origin,
        sort=s.sort,
        limit=s.limit,
        history_text=history_text,
    )
    fails: list[str] = []
    trips = _meta_value(metas, "trips") or []

    if s.min_rows is not None and len(trips) < s.min_rows:
        fails.append(f"expected >= {s.min_rows} trips, got {len(trips)}")
    if s.max_rows is not None and len(trips) > s.max_rows:
        fails.append(f"expected <= {s.max_rows} trips, got {len(trips)}")
    if s.price_order:
        prices = [t["price_egp"] for t in trips]
        if prices != sorted(prices, reverse=(s.price_order == "desc")):
            fails.append(f"prices not {s.price_order}: {prices}")
    if s.latest and trips:
        dts = [date.fromisoformat(t["date"]) for t in trips]
        if dts[-1] != max(dts):
            fails.append(f"latest: last row {dts[-1]} != max {max(dts)}")
    for c in s.contains:
        if c not in text and not any(c in str(t.values()) for t in trips):
            fails.append(f"missing text/route: {c!r}")
    for c in s.not_contains:
        if c in text or any(c in str(t.values()) for t in trips):
            fails.append(f"unexpected text/route: {c!r}")
    return fails


def check_station(db, s: Station) -> list[str]:
    _text, metas = execute_find_station(db, query=s.query)
    stations = _meta_value(metas, "stations") or []
    if s.expect_card and not stations:
        return ["expected a station card, got none"]
    if not s.expect_card and stations:
        return [f"expected no station card, got {len(stations)}"]
    return []


def check_dests(db, s: Dests) -> list[str]:
    _text, metas = execute_list_destinations(db)
    dests = _meta_value(metas, "destinations") or []
    return [] if dests else ["expected destination chips, got none"]


def check_kb(db, s: Kb) -> list[str]:
    text, _metas = execute_search_kb(db, query=s.query, topics=s.topics or None)
    fails = []
    for lbl in s.require:
        if f"[{lbl}]" not in text:
            fails.append(f"missing label [{lbl}]")
    return fails


SCENARIOS: list = [
    # --- trips: schedules & routes ---
    Trips("cairo-alex schedule", destination="alexandria", origin="cairo", min_rows=1),
    Trips("next to dahab", destination="dahab", min_rows=1),
    Trips("hurghada price", destination="hurghada", origin="cairo", min_rows=1),
    Trips("marsa alam", destination="marsa alam", origin="cairo", min_rows=1),
    Trips("port said open", destination="port said", origin="cairo", min_rows=1),
    Trips("arabic dest", destination="الإسكندرية", origin="القاهرة", min_rows=1),
    Trips("arabic plain alef", destination="الاسكندرية", min_rows=1),
    # --- trips: ordering / counts / latest ---
    Trips("latest to dahab", destination="dahab", sort="latest", min_rows=1, latest=True),
    Trips("latest 5 alex", destination="alexandria", origin="cairo", sort="latest",
          limit=5, min_rows=2, max_rows=5),
    Trips("cheapest alex", destination="alexandria", origin="cairo", sort="cheapest",
          min_rows=2, price_order="asc"),
    Trips("priciest alex", destination="alexandria", origin="cairo", sort="priciest",
          min_rows=2, price_order="desc"),
    # --- trips: follow-up route memory (destination resolved from history) ---
    Trips("followup latest 5", sort="latest", limit=5,
          history=["cairo to alexandria schedules", "here are the alexandria trips"],
          min_rows=1, max_rows=5, contains=["الإسكندرية"]),
    Trips("followup recency", sort="latest", limit=5,
          history=["trips to hurghada", "here are hurghada trips",
                   "cairo to alexandria schedules", "here are alexandria trips"],
          contains=["الإسكندرية"], not_contains=["الغردقة"]),
    # --- trips: boarding swap + no-data ---
    Trips("unserved origin", destination="hurghada", origin="giza", min_rows=1),
    Trips("unknown city", destination="atlantis", contains=[NO_TRIP_HINT]),
    # --- stations ---
    Station("station nasr city", "Nasr City"),
    Station("station giza", "Giza"),
    Station("arabic station", "مدينة نصر"),
    # --- destinations ---
    Dests("destinations list"),
    # --- knowledge base ---
    Kb("booking how-to", "How can I book a GoBus ticket?", topics=["faq"], require=["FAQ"]),
    Kb("services vs gomini", "Difference between GoBus and GoMini?",
       topics=["services"], require=["Services"]),
    Kb("about company", "Who owns GoBus and when was it founded?",
       topics=["about"], require=["About"]),
    Kb("policy cancel", "What is the cancellation and refund policy?",
       topics=["policies"], require=["Policies"]),
    Kb("destination hurghada", "Tell me about Hurghada as a destination",
       topics=["destinations"], require=["Destinations"]),
]


def run_one(db, s) -> list[str]:
    if isinstance(s, Trips):
        return check_trips(db, s)
    if isinstance(s, Station):
        return check_station(db, s)
    if isinstance(s, Dests):
        return check_dests(db, s)
    if isinstance(s, Kb):
        return check_kb(db, s)
    return [f"unknown scenario type: {type(s)}"]


def main() -> int:
    db = SessionLocal()
    passed = failed = 0
    print("GOBUS BOT TOOL-EXECUTOR BEHAVIORAL SUITE")
    print("=" * 92)
    for s in SCENARIOS:
        fails = run_one(db, s)
        if fails:
            failed += 1
            print(f"FAIL | {s.name}")
            for f in fails:
                print(f"       - {f}")
        else:
            passed += 1
            print(f"PASS | {s.name}")
    print("=" * 92)
    print(f"Summary: {passed} passed, {failed} failed, {len(SCENARIOS)} total")
    db.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

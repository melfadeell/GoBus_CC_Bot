"""LLM tool definitions + executors for the contextual chat agent.

The chat LLM decides what to do by calling these tools; each executor runs the
existing safe SQLAlchemy queries in ``kb_retrieval`` (no raw model-generated SQL)
and returns ``(result_text, meta_events)``:

- ``result_text`` is fed back to the model as the tool result so it can write a
  short reply.
- ``meta_events`` are SSE ``meta`` dicts (trips/stations/destinations/ticket
  cards) the frontend renders deterministically — the model never formats them.

This replaces the old regex/keyword understanding layer and the per-branch
prompt directives.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.models import Ticket
from app.services.kb_retrieval import (
    VALID_KB_TOPICS,
    _all_route_destinations,
    _expand_search_terms,
    _fetch_station_blocks,
    _fetch_trip_blocks,
    _match_served_destination,
    fetch_kb_topic_blocks,
)
from app.services.ticketing_agent import build_ticket_draft

settings = get_settings()

VALID_TRIP_SORT = ("soonest", "latest", "cheapest", "priciest")
VALID_BUS_CLASS = ("standard", "elite", "business")


# --- Tool schemas (OpenAI function-calling format) -------------------------------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_trips",
            "description": (
                "Find live GoBus bus trips (schedules, prices, seats, classes) for a "
                "route. Use for any question about trips, schedules, prices, seats, the "
                "next/last/cheapest trip, 'I want to go to X', or 'where do I board'. "
                "Resolve origin/destination from the conversation for follow-ups like "
                "'the cheapest one' or 'show 5 more'. City names may be in Arabic, "
                "English, or Franco-Arabic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destination_city": {
                        "type": "string",
                        "description": "Arrival city (any language), e.g. 'Hurghada' or 'الغردقة'.",
                    },
                    "origin_city": {
                        "type": "string",
                        "description": "Departure city (any language). Omit if unknown.",
                    },
                    "sort": {
                        "type": "string",
                        "enum": list(VALID_TRIP_SORT),
                        "description": "Ordering: soonest (default), latest, cheapest, priciest.",
                    },
                    "bus_class": {
                        "type": "string",
                        "enum": list(VALID_BUS_CLASS),
                        "description": "Only when the customer asks for one specific class.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of trips to show (1-12) when the customer asks for N.",
                    },
                },
                "required": ["destination_city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_station",
            "description": (
                "Look up a GoBus station / office by city or area name to get its address, "
                "working hours, and map link. Use for 'where is X station', 'nearest "
                "station', 'map/address/working hours'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Station, city, or area name (any language).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_destinations",
            "description": (
                "List the cities/destinations GoBus serves, or check whether GoBus goes to "
                "ONE specific city. Use without arguments for 'which destinations do you "
                "serve', 'where do you go', 'what cities'. Pass the `city` argument for a "
                "yes/no question about a single place, e.g. 'Do you go to Sharm El Sheikh?', "
                "'Does GoBus reach Luxor?', 'هل جوباص بيروح الغردقة؟'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": (
                            "A single city/destination to check (any language). Omit to list "
                            "all destinations."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the GoBus knowledge base for non-schedule info: how to book, app "
                "help, hotline, bus classes (Standard/Elite/Business), GoMini/GoLemo, "
                "company/about info, refund/cancellation/privacy policies, and destination "
                "city guides. Use for any informational question that is NOT a live trip, "
                "station lookup, or support ticket."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The customer's question / search text.",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(VALID_KB_TOPICS)},
                        "description": "Which KB areas to search; pick all that apply.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_support_ticket",
            "description": (
                "Begin filing a customer-support complaint/ticket (NOT booking a bus). Use "
                "when the customer reports a problem or wants to complain. The backend "
                "decides whether enough detail was given to show a confirmation form, or "
                "whether to ask for more detail first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_summary": {
                        "type": "string",
                        "description": "Short summary of the issue, if the customer described it.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_support_tickets",
            "description": (
                "Look up the customer's existing support tickets / complaint status. Use "
                "for 'my tickets', 'ticket status', or a GB-YYYY-NNNN reference."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# --- Executors -------------------------------------------------------------------


def _meta(payload: dict) -> dict:
    return {"type": "meta", **payload}


def execute_search_trips(
    db: Session,
    *,
    destination_city: str | None = None,
    origin_city: str | None = None,
    sort: str = "soonest",
    bus_class: str | None = None,
    limit: int | None = None,
    history_text: str | None = None,
) -> tuple[str, list[dict]]:
    parts: list[str] = []
    if origin_city and origin_city.strip():
        parts.append(f"from {origin_city.strip()}")
    if destination_city and destination_city.strip():
        parts.append(f"to {destination_city.strip()}")
    query_text = " ".join(parts).strip()

    if not query_text and not history_text:
        return (
            "[Trips] No route was given. Ask the customer for their origin and destination "
            "city.",
            [],
        )

    if sort not in VALID_TRIP_SORT:
        sort = "soonest"
    if bus_class not in VALID_BUS_CLASS:
        bus_class = None
    if limit is not None and not (1 <= limit <= 12):
        limit = None

    # Only expand the CURRENT turn's cities. History resolution flows through
    # ``fallback_text`` so a pure follow-up ("the latest 5") uses the most recent
    # route rather than unioning every route mentioned earlier.
    search_terms = _expand_search_terms(query_text, db)
    debug: dict = {}
    blocks = _fetch_trip_blocks(
        db,
        query_text,
        search_terms,
        sort=sort,
        bus_class=bus_class,
        limit=limit,
        debug=debug,
        fallback_text=history_text,
    )

    meta_events: list[dict] = []
    if debug.get("trips"):
        meta_events.append(_meta({"trips": debug["trips"]}))
    # A boarding recommendation surfaces the nearest origin's station card too.
    if debug.get("stations"):
        meta_events.append(_meta({"stations": debug["stations"]}))
    if debug.get("trips_sql") and settings.expose_sql_debug:
        meta_events.append(_meta({"sql": debug["trips_sql"]}))

    return "\n\n".join(blocks), meta_events


def execute_find_station(db: Session, *, query: str) -> tuple[str, list[dict]]:
    q = (query or "").strip()
    if not q:
        return ("[Stations] No station/area name was given. Ask which station they mean.", [])
    search_terms = _expand_search_terms(q, db)
    debug: dict = {}
    blocks = _fetch_station_blocks(db, q, search_terms, debug=debug)
    meta_events: list[dict] = []
    if debug.get("stations"):
        meta_events.append(_meta({"stations": debug["stations"]}))
    return "\n\n".join(blocks), meta_events


def execute_list_destinations(
    db: Session, *, city: str | None = None
) -> tuple[str, list[dict]]:
    dests = _all_route_destinations(db)
    if not dests:
        return ("[Destinations] No destinations are configured.", [])

    # Single-city yes/no check ("Does GoBus go to Sharm El Sheikh?"). Confirm or deny
    # plainly in one line — do NOT dump the whole destinations chip list for this.
    if city and city.strip():
        matched = _match_served_destination(db, city)
        if matched:
            return (
                f"[Destinations] YES — GoBus serves this city (stored as '{matched}'). Confirm "
                "to the customer in ONE short line that GoBus goes there, using the city name "
                "in the customer's own language/spelling, and offer to show trips or the "
                "station there. Do NOT list all other destinations.",
                [],
            )
        return (
            f"[Destinations] NO — '{city.strip()}' is not among GoBus destinations. Tell the "
            "customer plainly in one line that GoBus does not currently serve it, then show "
            "the full list of served destinations as chips below.",
            [_meta({"destinations": dests})],
        )

    return (
        "[Destinations] The full list of GoBus destinations is shown to the user as chips "
        "below. Reply with a short one-line intro only.",
        [_meta({"destinations": dests})],
    )


def execute_search_kb(
    db: Session, *, query: str, topics: list[str] | None = None
) -> tuple[str, list[dict]]:
    text = fetch_kb_topic_blocks(db, query, topics)
    if not text:
        text = (
            "No specific GoBus match was found for this. Answer helpfully and briefly from "
            "general GoBus knowledge, or point the customer to the hotline {{HOTLINE}}. Do "
            "NOT tell the customer this was missing from a knowledge base, database, or "
            "context — just answer naturally as GoBus."
        )
    return text, []


def fetch_ticket_summaries(db: Session, customer_id: int, limit: int = 10) -> list[dict]:
    """Compact ticket rows for the chat follow-up cards (plain dicts so nothing
    detached is accessed from the async context)."""
    rows = (
        db.query(Ticket)
        .filter(Ticket.customer_id == customer_id)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "ref_number": t.ref_number,
            "subject": t.subject,
            "category": t.category,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


async def _execute_start_ticket(
    history: list[dict],
    message: str,
    customer_id: int | None,
    channel: str,
) -> tuple[str, list[dict]]:
    draft = await build_ticket_draft(history, message)
    if draft.get("ready"):
        meta = _meta(
            {
                "action": "open_ticket_form",
                "draft": draft,
                "logged_in": customer_id is not None,
                "channel": channel,
            }
        )
        return (
            "A pre-filled ticket form is shown to the customer below to review and confirm. "
            "Reply with ONE short line telling them to review and confirm it; do NOT ask for "
            "the details again and do NOT claim a ticket was created.",
            [meta],
        )
    return (
        "Not enough detail yet. Ask the customer ONE short, friendly question to describe "
        "what happened (what, when, which trip/route if relevant) so a ticket can be opened. "
        "Do NOT show a form or claim a ticket was created.",
        [],
    )


async def _execute_check_tickets(
    db: Session, customer_id: int | None
) -> tuple[str, list[dict]]:
    if customer_id is None:
        return (
            "The customer is not logged in. Politely ask them to log in or create an account "
            "to view their tickets. Keep it to one or two short lines.",
            [_meta({"action": "login_required"})],
        )
    tickets = await asyncio.to_thread(fetch_ticket_summaries, db, customer_id)
    return (
        "The customer's tickets are shown as cards below. Reply with ONE short line (e.g. "
        "'Here are your tickets:'); do NOT list or invent ticket details yourself.",
        [_meta({"tickets_crm": tickets})],
    )


async def run_tool(
    name: str,
    args: dict,
    *,
    db: Session,
    message: str,
    history: list[dict],
    history_text: str | None,
    customer_id: int | None,
    channel: str,
) -> tuple[str, list[dict]]:
    """Dispatch a tool call to its executor. DB-bound sync work runs off the loop.

    Never raises — returns a short error string so the chat turn always completes.
    """
    try:
        if name == "search_trips":
            return await asyncio.to_thread(
                execute_search_trips,
                db,
                destination_city=args.get("destination_city"),
                origin_city=args.get("origin_city"),
                sort=args.get("sort") or "soonest",
                bus_class=args.get("bus_class"),
                limit=args.get("limit"),
                history_text=history_text,
            )
        if name == "find_station":
            return await asyncio.to_thread(
                execute_find_station, db, query=args.get("query") or message
            )
        if name == "list_destinations":
            return await asyncio.to_thread(
                execute_list_destinations, db, city=args.get("city")
            )
        if name == "search_knowledge_base":
            return await asyncio.to_thread(
                execute_search_kb,
                db,
                query=args.get("query") or message,
                topics=args.get("topics"),
            )
        if name == "start_support_ticket":
            return await _execute_start_ticket(history, message, customer_id, channel)
        if name == "check_support_tickets":
            return await _execute_check_tickets(db, customer_id)
    except Exception as exc:  # pragma: no cover - never break the chat turn
        return (f"[tool error] {name} failed: {exc}", [])

    return (f"[tool error] unknown tool: {name}", [])

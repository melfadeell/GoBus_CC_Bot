"""
End-to-end chat test: POST /api/chat/stream and validate assistant replies.

Usage:
  cd backend
  .\\venv\\Scripts\\python scripts\\test_chat_e2e.py

Output: ../CHAT_E2E_TEST_RESULTS.md
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "CHAT_E2E_TEST_RESULTS.md"
REQUEST_GAP_SEC = 5  # stay under 15 chat messages/minute rate limit

FAIL_PHRASES = [
    "don't have the specific schedule",
    "don't have specific schedule",
    "i don't have the specific",
    "i don't have information about",
    "i'm sorry, but i don't have",
]

TRIP_FAIL_PHRASES = FAIL_PHRASES + [
    "recommend checking the gobus website",
    "contacting their hotline at 19567",
]


@dataclass
class Scenario:
    question: str
    category: str
    must_contain_any: list[str] = field(default_factory=list)
    must_contain_all: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    min_length: int = 80


SCENARIOS: list[Scenario] = [
    Scenario(
        "What is the difference between GoBus and GoMini?",
        "Services",
        must_contain_any=["gobus", "gomini"],
    ),
    Scenario(
        "Nearest GoBus station in Nasr City?",
        "Stations",
        must_contain_any=["nasr", "نصر", "station", "محطة", "map", "خريطة"],
    ),
    Scenario(
        "Cairo – Alexandria trip schedules",
        "Trips",
        must_contain_any=["alexandria", "الإسكندرية", "egp", "06:", "08:", "departure", "مغادرة"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "What is the next trip to Dahab?",
        "Trips",
        must_contain_any=["dahab", "دهب", "egp", "06:", "08:", "trip", "رحلة"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "How can I book a GoBus ticket?",
        "FAQ",
        must_contain_any=["book", "online", "19567", "website", "حجز"],
    ),
    Scenario(
        "Trip prices from Cairo to Hurghada",
        "Trips",
        must_contain_any=["hurghada", "الغردقة", "egp", "جنيه", "price", "سعر"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "Tell me about GoBus destinations",
        "Destinations",
        must_contain_any=["destination", "dahab", "hurghada", "alexandria", "sharm", "وجه"],
    ),
    Scenario(
        "What is the GoBus hotline?",
        "FAQ",
        must_contain_all=["19567"],
    ),
    Scenario(
        "Seats available tomorrow to Sharm El Sheikh?",
        "Trips",
        must_contain_any=["sharm", "شرم", "seat", "مقعد", "available", "egp", "open"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "What bus classes does GoBus offer?",
        "FAQ",
        must_contain_any=["standard", "elite", "business"],
    ),
    Scenario(
        "Who owns GoBus and when was it founded?",
        "About",
        must_contain_any=["gobus", "company", "founded", "history", "شركة", "تأسست"],
    ),
    Scenario(
        "What is GoLemo and what services does it offer?",
        "Services",
        must_contain_any=["golemo", "gol emo", "جوليمو", "service", "transport"],
    ),
    Scenario(
        "What is the cancellation and refund policy?",
        "Policies",
        must_contain_any=["cancel", "refund", "policy", "إلغاء", "استرداد", "19567"],
    ),
    Scenario(
        "Tell me about Hurghada as a destination",
        "Destinations",
        must_contain_any=["hurghada", "الغردقة", "destination", "red sea", "البحر"],
    ),
    Scenario(
        "Where is the Giza station and what is the map link?",
        "Stations",
        must_contain_any=["giza", "الجيزة", "map", "http", "خريطة", "station", "محطة"],
    ),
    Scenario(
        "Cairo to Marsa Alam schedule",
        "Trips",
        must_contain_any=["marsa", "مرسى", "egp", "06:", "08:", "schedule", "departure"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "Are there open trips from Cairo to Port Said?",
        "Trips",
        must_contain_any=["port said", "بور", "egp", "trip", "open", "seat", "مقعد"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "How do I know trip schedules?",
        "FAQ",
        must_contain_any=["schedule", "trip", "assistant", "ask", "مواعيد", "رحلة"],
    ),
    Scenario(
        "What destinations does GoBus serve?",
        "Destinations",
        must_contain_any=["destination", "dahab", "hurghada", "alexandria", "sharm", "luxor"],
    ),
    Scenario(
        "Nearest GoBus station in Heliopolis?",
        "Stations",
        must_contain_any=["heliopolis", "مصر الجديدة", "الماظة", "station", "محطة", "map"],
    ),
    Scenario(
        "What is the price for Cairo to Alexandria elite class?",
        "Trips",
        must_contain_any=["alexandria", "الإسكندرية", "elite", "egp", "price"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "Can I book tickets online?",
        "FAQ",
        must_contain_any=["online", "book", "website", "حجز", "19567"],
    ),
    Scenario(
        "Tell me about GoBus company history",
        "About",
        must_contain_any=["gobus", "history", "company", "founded", "شركة"],
    ),
    Scenario(
        "What are the terms and conditions?",
        "Policies",
        must_contain_any=["terms", "conditions", "policy", "شروط", "19567"],
    ),
    Scenario(
        "Tell me about Dahab",
        "Destinations",
        must_contain_any=["dahab", "دهب", "destination", "sinai", "سيناء"],
    ),
    Scenario(
        "What is the difference between standard and elite?",
        "FAQ",
        must_contain_any=["standard", "elite", "class", "comfort", "business"],
    ),
    Scenario(
        "Trip from Cairo to Luxor tomorrow",
        "Trips",
        must_contain_any=["luxor", "الأقصر", "egp", "trip", "06:", "08:", "tomorrow"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
    Scenario(
        "Where is Madinaty station?",
        "Stations",
        must_contain_any=["madinaty", "مدينتي", "station", "محطة", "map", "http"],
    ),
    Scenario(
        "What is GoMini?",
        "Services",
        must_contain_any=["gomini", "go mini", "جوميني", "group", "transport"],
    ),
    Scenario(
        "Seats available on Cairo to Nuweiba trips?",
        "Trips",
        must_contain_any=["nuweiba", "نويبع", "seat", "مقعد", "egp", "available", "open"],
        must_not_contain=TRIP_FAIL_PHRASES,
    ),
]


@dataclass
class Result:
    scenario: Scenario
    status: str
    response: str
    issues: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_sec: float = 0.0


def parse_sse_response(raw: str) -> tuple[str, str | None]:
    """Parse SSE body; return (assistant_text, error_message)."""
    text_parts: list[str] = []
    error_msg: str | None = None
    event_name = ""
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            payload = line[5:].strip()
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if event_name == "token" and "content" in data:
                text_parts.append(data["content"])
            elif event_name == "error" and "error" in data:
                error_msg = data["error"]
    return "".join(text_parts).strip(), error_msg


def stream_chat(client: httpx.Client, message: str) -> tuple[str, str | None, float]:
    session_id = f"e2e-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    with client.stream(
        "POST",
        f"{BASE_URL}/api/chat/stream",
        json={"message": message, "session_id": session_id, "channel": "website"},
        headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        timeout=120.0,
    ) as response:
        if response.status_code == 429:
            return "", "Rate limited (429)", time.perf_counter() - started
        response.raise_for_status()
        raw = response.read().decode("utf-8", errors="replace")
    elapsed = time.perf_counter() - started
    text, err = parse_sse_response(raw)
    return text, err, elapsed


def evaluate(scenario: Scenario, response: str, error: str | None) -> tuple[str, list[str]]:
    if error:
        return "FAIL", [error]
    if not response:
        return "FAIL", ["Empty assistant response"]

    lowered = response.lower()
    issues: list[str] = []

    if len(response) < scenario.min_length:
        issues.append(f"Response too short ({len(response)} chars, min {scenario.min_length})")

    for phrase in scenario.must_not_contain:
        if phrase.lower() in lowered:
            issues.append(f"Unwanted phrase: {phrase}")

    if scenario.must_contain_all:
        for token in scenario.must_contain_all:
            if token.lower() not in lowered:
                issues.append(f"Missing required: {token}")

    if scenario.must_contain_any:
        if not any(token.lower() in lowered for token in scenario.must_contain_any):
            issues.append(f"Missing any of: {', '.join(scenario.must_contain_any[:6])}…")

    return ("PASS", []) if not issues else ("FAIL", issues)


def render_markdown(results: list[Result], started_at: str, total_sec: float) -> str:
    passed = sum(1 for r in results if r.status == "PASS")
    failed = len(results) - passed

    lines = [
        "# Chat E2E Test Results",
        "",
        f"**Run at:** {started_at} UTC  ",
        f"**Endpoint:** `{BASE_URL}/api/chat/stream`  ",
        f"**Duration:** {total_sec:.1f}s  ",
        f"**Summary:** {passed} passed, {failed} failed, {len(results)} total",
        "",
        "## Summary table",
        "",
        "| # | Status | Category | Question |",
        "|---|--------|----------|----------|",
    ]

    for i, r in enumerate(results, 1):
        q = r.scenario.question.replace("|", "\\|")
        icon = "✅" if r.status == "PASS" else "❌"
        lines.append(f"| {i} | {icon} {r.status} | {r.scenario.category} | {q} |")

    lines.extend(["", "## Details", ""])

    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.scenario.question}")
        lines.append("")
        lines.append(f"- **Category:** {r.scenario.category}")
        lines.append(f"- **Status:** {r.status}")
        lines.append(f"- **Time:** {r.elapsed_sec:.1f}s")
        if r.issues:
            lines.append(f"- **Issues:** {'; '.join(r.issues)}")
        lines.append("")
        lines.append("**Assistant reply (truncated):**")
        lines.append("")
        preview = r.response[:1200] + ("…" if len(r.response) > 1200 else "")
        lines.append("```")
        lines.append(preview or "(empty)")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    run_started = time.perf_counter()

    try:
        health = httpx.get(f"{BASE_URL}/api/health", timeout=10.0)
        health.raise_for_status()
    except Exception as exc:
        OUTPUT_PATH.write_text(
            f"# Chat E2E Test Results\n\nBackend not reachable at `{BASE_URL}`: {exc}\n",
            encoding="utf-8",
        )
        print(f"Backend down: {exc}")
        return 1

    results: list[Result] = []
    with httpx.Client() as client:
        for idx, scenario in enumerate(SCENARIOS):
            if idx > 0:
                time.sleep(REQUEST_GAP_SEC)
            try:
                response, error, elapsed = stream_chat(client, scenario.question)
            except Exception as exc:
                response, error, elapsed = "", str(exc), 0.0

            status, issues = evaluate(scenario, response, error)
            result = Result(
                scenario=scenario,
                status=status,
                response=response,
                issues=issues,
                error=error,
                elapsed_sec=elapsed,
            )
            results.append(result)
            mark = "PASS" if status == "PASS" else "FAIL"
            print(f"[{idx + 1}/{len(SCENARIOS)}] {mark} | {scenario.category} | {scenario.question[:55]}")

    total_sec = time.perf_counter() - run_started
    md = render_markdown(results, started_at, total_sec)
    OUTPUT_PATH.write_text(md, encoding="utf-8")
    print()
    print(f"Wrote {OUTPUT_PATH}")
    passed = sum(1 for r in results if r.status == "PASS")
    print(f"Summary: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Measure time-to-first-token (TTFT) for a set of chat questions.

Hits POST /api/chat/stream and records the wall-clock time from sending the
request to receiving the first streamed token, plus total completion time.

Usage (backend running on :8000):
  venv/Scripts/python.exe scripts/test_ttft.py
Output: ../TTFT_RESULTS.md
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "TTFT_RESULTS.md"
GAP_SEC = 2.0
TTFT_BUDGET_SEC = 4.0

QUESTIONS = [
    "What is the difference between GoBus and GoMini?",
    "Nearest GoBus station in Nasr City?",
    "Cairo – Alexandria trip schedules",
    "What is the next trip to Dahab?",
    "How can I book a GoBus ticket?",
    "Trip prices from Cairo to Hurghada",
    "Tell me about GoBus destinations",
    "What is the GoBus hotline?",
    "Seats available tomorrow to Sharm El Sheikh?",
    "What bus classes does GoBus offer?",
]


def measure(client: httpx.Client, question: str) -> tuple[float, float, bool]:
    """Return (ttft_sec, total_sec, ok)."""
    session_id = f"ttft-{uuid.uuid4().hex[:10]}"
    started = time.perf_counter()
    ttft: float | None = None
    got_token = False
    event_name = ""
    with client.stream(
        "POST",
        f"{BASE_URL}/api/chat/stream",
        json={"message": question, "session_id": session_id, "channel": "website"},
        headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        timeout=120.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:") and event_name == "token":
                if ttft is None:
                    ttft = time.perf_counter() - started
                    got_token = True
    total = time.perf_counter() - started
    return (ttft if ttft is not None else total), total, got_token


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        httpx.get(f"{BASE_URL}/api/health", timeout=10.0).raise_for_status()
    except Exception as exc:
        print(f"Backend down: {exc}")
        return 1

    rows: list[tuple[int, str, float, float, bool]] = []
    with httpx.Client() as client:
        for i, q in enumerate(QUESTIONS, 1):
            if i > 1:
                time.sleep(GAP_SEC)
            try:
                ttft, total, ok = measure(client, q)
            except Exception as exc:
                print(f"[{i}] ERROR: {exc}")
                rows.append((i, q, 0.0, 0.0, False))
                continue
            within = ok and ttft <= TTFT_BUDGET_SEC
            rows.append((i, q, ttft, total, within))
            print(f"[{i:2}] TTFT={ttft:5.2f}s total={total:6.2f}s {'OK' if within else 'SLOW'} | {q[:45]}")

    ttfts = [r[2] for r in rows if r[4] or r[2] > 0]
    avg = sum(r[2] for r in rows) / len(rows) if rows else 0
    within_budget = sum(1 for r in rows if r[4])
    fastest = min(ttfts) if ttfts else 0
    slowest = max(ttfts) if ttfts else 0

    lines = [
        "# Chat TTFT (time-to-first-token) Results",
        "",
        f"**Run at:** {started_at} UTC  ",
        f"**Endpoint:** `{BASE_URL}/api/chat/stream`  ",
        f"**TTFT budget:** {TTFT_BUDGET_SEC:.0f}s  ",
        f"**Within budget:** {within_budget}/{len(rows)}  ",
        f"**Avg TTFT:** {avg:.2f}s · **Fastest:** {fastest:.2f}s · **Slowest:** {slowest:.2f}s",
        "",
        "| # | Question | TTFT (s) | Total (s) | ≤ budget |",
        "|---|----------|----------|-----------|----------|",
    ]
    for i, q, ttft, total, ok in rows:
        icon = "✅" if ok else "❌"
        lines.append(f"| {i} | {q.replace('|', chr(92) + '|')} | {ttft:.2f} | {total:.2f} | {icon} |")
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH}")
    print(f"Within budget: {within_budget}/{len(rows)} | avg TTFT {avg:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

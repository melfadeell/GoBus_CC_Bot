"""Run every demo question (from the frontend translations) through the real chat
pipeline and report the response + structured meta, flagging anything suspicious."""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

# Seconds between questions — keep us under the provider's 20 requests/minute cap
# (each question makes up to 2 LLM calls: rewrite + reply).
GAP = float(os.environ.get("GAP", "7"))
ONLY = os.environ.get("ONLY", "")  # "ar" or "en" to run one locale

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.services.chat_service import stream_chat_response

TRANSLATIONS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "translations.ts"

REFUSAL_PATTERNS = [
    "لا أستطيع", "لا يمكنني", "لا تتوفر", "لا توجد لدي", "غير متاح", "ليس لدي",
    "لا أملك", "تطبيق جوباص", "can't provide", "cannot provide", "don't have",
    "do not have", "unable to", "no information", "check the app", "in the gobus app",
]


def extract_questions() -> dict[str, list[str]]:
    src = TRANSLATIONS.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for label, start in (("ar", 0), ("en", 1)):
        positions = [m.start() for m in re.finditer(r"demoCategories:", src)]
        block_start = positions[start]
        i = src.index("[", block_start)
        depth = 0
        j = i
        while j < len(src):
            if src[j] == "[":
                depth += 1
            elif src[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        arr = src[i : j + 1]
        q_blocks = re.findall(r"questions:\s*\[(.*?)\]", arr, re.S)
        out[label] = re.findall(r"'([^']+)'", "\n".join(q_blocks))
    return out


async def ask(question: str, idx: int) -> dict:
    db = SessionLocal()
    text = ""
    meta = {"trips": 0, "stations": 0, "destinations": 0, "action": None}
    error = None
    try:
        async for ev in stream_chat_response(
            db, f"demoQ-{idx}", question, channel="website"
        ):
            if ev["type"] == "token":
                text += ev["content"]
            elif ev["type"] == "meta":
                if ev.get("trips"):
                    meta["trips"] = len(ev["trips"])
                if ev.get("stations"):
                    meta["stations"] = len(ev["stations"])
                if ev.get("destinations"):
                    meta["destinations"] = len(ev["destinations"])
                if ev.get("action"):
                    meta["action"] = ev["action"]
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()
    return {"text": text.strip(), "meta": meta, "error": error}


def classify(q: str, r: dict) -> str:
    if r["error"]:
        return "ERROR"
    if not r["text"]:
        return "EMPTY"
    has_data = any(r["meta"][k] for k in ("trips", "stations", "destinations")) or r["meta"]["action"]
    low = r["text"].lower()
    refused = any(p.lower() in low for p in REFUSAL_PATTERNS)
    # A refusal is only a problem if we ALSO didn't render real data.
    if refused and not has_data:
        return "REFUSAL?"
    return "OK"


async def main() -> int:
    questions = extract_questions()
    flagged: list[str] = []
    locales = (ONLY,) if ONLY else ("ar", "en")
    for locale in locales:
        qs = questions[locale]
        print(f"\n================= {locale.upper()} ({len(qs)} questions) =================")
        for i, q in enumerate(qs):
            if i:
                await asyncio.sleep(GAP)
            r = await ask(q, f"{locale}-{i}")
            tag = classify(q, r)
            m = r["meta"]
            meta_bits = []
            if m["trips"]:
                meta_bits.append(f"trips={m['trips']}")
            if m["stations"]:
                meta_bits.append(f"stations={m['stations']}")
            if m["destinations"]:
                meta_bits.append(f"dest={m['destinations']}")
            if m["action"]:
                meta_bits.append(f"action={m['action']}")
            meta_str = " ".join(meta_bits) or "-"
            snippet = (r["text"] or r["error"] or "")[:90].replace("\n", " ")
            print(f"[{tag:8}] {q[:42]:42} | {meta_str:22} | {snippet}")
            if tag != "OK":
                flagged.append(f"{locale}: {q}  ->  [{tag}] {snippet}")

    print("\n================= SUMMARY =================")
    if flagged:
        print(f"{len(flagged)} flagged:")
        for f in flagged:
            print("  -", f)
    else:
        print("All questions returned OK responses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

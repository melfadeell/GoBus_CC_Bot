# GoBus Chatbot — Conversation Flow & Logic

This document maps the full runtime behaviour of the bot: what happens for any
message, which branch it takes, and **when it says what (and when it doesn't)**.

> Diagrams are [Mermaid](https://mermaid.js.org/). They render automatically on
> GitHub and in VS Code (with a Mermaid preview extension).

Source of truth in code:
- `backend/app/services/chat_service.py` — the per-message pipeline
- `backend/app/services/kb_retrieval.py` — intent detection + data fetching
- `backend/app/services/ticketing_agent.py` + `ticket_intent.py` — tickets
- `backend/app/core/guardrails.py` — hard refusals
- `frontend/src/components/chat/*` — deterministic rendering of cards/tables

---

## 1. Conversation start — greeting (channel-aware)

```mermaid
flowchart TD
    A([Chat opens]) --> B{Channel?}
    B -->|website| C[Show greeting bubble on page load]
    C --> D{Customer logged in?}
    D -->|yes| E["Greet by name — مرحباً {name}!"]
    D -->|no| F["Generic greeting"]
    B -->|"social: whatsapp / instagram / facebook / tiktok / linkedin"| G[No proactive greeting]
    G --> H[Wait for the customer's first message]
    H --> I["Backend greets AND answers in the same first reply"]
```

- **Website** = proactive greeting on load, personalized when logged in.
- **Social** = message-triggered: the bot greets on the first inbound message,
  then answers it in the same reply (greeting alone, or greeting + answer).

---

## 2. Per-message pipeline (runs for every message)

```mermaid
flowchart TD
    M([User message]) --> S1["1 - Store message + load short history<br/>(last 5 user / 5 assistant)"]
    S1 --> S2{Needs rewrite?}
    S2 -->|"yes (non-trivial msg)"| R["2 - correct_query: franco / EN place names to Arabic<br/>used ONLY as extra search terms"]
    S2 -->|no| S3
    R --> S3["3 - retrieve_context: detect intents + fetch data"]
    S3 --> S4["4 - Ticket-intent gate (raise / check)"]
    S4 --> S5["5 - Emit META events to the UI"]
    S5 --> S6["6 - Build system prompt:<br/>guardrails + bot prompt + format rules + ticket directive + language rule + KB context"]
    S6 --> S7["7 - Stream LLM reply (first token emits ttft_ms)"]
    S7 --> S8["8 - Persist reply + fire-and-forget logs<br/>(chat_turn, llm_call, metrics, customer_id)"]
```

> The **original** message always drives intent + the answer. A bad rewrite can
> only add place-matching terms — it can never change *what kind* of answer you get.

---

## 3. Intent routing — what kind of answer you get

```mermaid
flowchart TD
    Q([User query]) --> I{Detect content intents}
    I -->|"trip words / route + date / cheapest / latest / seats"| T["TRIPS table — live SQL"]
    I -->|"station name or area mention"| ST["STATION card"]
    I -->|"destinations topic — وجهات"| D["DESTINATION chips — from DB"]
    I -->|"services / bus classes"| SV["SERVICES + KB article"]
    I -->|"booking / FAQ"| FQ["KB FAQ"]
    I -->|"company / about / policies"| KB["KB about / policies"]
    I -->|"no intent matched"| FB["Fallback: FAQ KB (+ trips/dest if hinted)"]

    T -.guard.-> G1["A route endpoint city is NOT shown as a station card<br/>(e.g. 'trip to Dahab' shows trips, not a Dahab station)"]
    ST -.guard.-> G2["A bare area name triggers a card even without the word 'station'<br/>but short generic words match only on word boundaries"]
    T -.follow-up.-> G3["'the latest 5' with no route → route recovered from history"]
```

Each matched intent fetches structured data and emits a **meta** event; the
model is told that data is shown and to write only a one-line intro.

---

## 4. Ticket sub-flow (agentic complaint / follow-up)

```mermaid
flowchart TD
    TQ([Message]) --> TI{detect_ticket_intent}

    TI -->|"raise (complaint / شكوى / مشكلة / file a complaint)"| AG[Ticketing agent reads the conversation]
    AG --> RD{Enough detail? - ready}
    RD -->|no| ASK["raise_collect → bot ASKS:<br/>'what happened? when? which trip?'  (NO form)"]
    RD -->|yes| FORM["meta: open_ticket_form (pre-filled draft:<br/>subject + details; category/priority hidden)"]
    FORM --> CONF{Confirm?}
    CONF -->|"guest"| OTP["collect name + email + phone → email OTP → verify"]
    CONF -->|"logged in"| CREATE
    OTP --> CREATE["POST /api/tickets"]
    CREATE --> DONE["Ref GB-YYYY-NNNNNN + 'confirmation email sent'<br/>(created email with name + table)"]

    TI -->|"check (my ticket / حالة التذكرة / GB-2026-...)"| CK{Logged in?}
    CK -->|yes| CARDS["meta: tickets_crm cards + one-line intro"]
    CK -->|no| LOGIN["meta: login_required → bot asks to log in"]

    TI -->|none| NORMAL[Normal pipeline - section 3]
```

> The raise flow only continues from the **immediately preceding** turn — an
> earlier, already-handled complaint can't hijack a later unrelated question
> (and a trip/station/destination query is never treated as a complaint).

---

## 5. Guardrails (hard refusals — server-side, override everything)

```mermaid
flowchart TD
    GQ([Any request]) --> GG{Off-limits topic?}
    GG -->|no| OK[Proceed normally]
    GG -->|"religion / hate / NSFW / illegal / weapons / malware / political / impersonation / private PII"| REF["Refuse cleanly + pivot to GoBus help + hotline"]
    GG -->|"self-harm / intent to harm others"| CARE["Care protocol + crisis resources (no alternatives)"]
    GG -->|"minors in exploitative context"| ABS["Absolute refusal — no exceptions"]
```

---

## 6. Meta events → what renders in the UI

```mermaid
flowchart LR
    P[stream_chat_response] --> E1["sql (debug only, off in prod)"] --> U1[SQL bubble]
    P --> E2[stations] --> U2[Station card]
    P --> E3[destinations] --> U3[Destination chips]
    P --> E4[trips] --> U4["Trips table (From/To station, date, class, seats, price)"]
    P --> E5["action: open_ticket_form + draft"] --> U5[Ticket confirm form]
    P --> E6[tickets_crm] --> U6[Ticket status cards]
    P --> E7["action: login_required"] --> U7[Login prompt]
    P --> E8[ttft_ms] --> U8[Response-time badge]
    P --> E9[token stream] --> U9[Assistant text bubble]
```

Order emitted: `ticket → sql → stations → destinations → trips → (social greeting) → tokens`.

---

## 7. When it says what — and when it doesn't

| Situation | It SAYS | It does NOT say |
|---|---|---|
| Trips / stations / destinations found | one short intro line ("Here are the trips…", "تفضل تفاصيل المحطة:") | never re-lists rows; never invents trips/prices/stations |
| Station resolved (incl. city → main station) | affirms + shows the card | never "I can't provide / check the app" |
| No trips for that route | "no trips" + suggested alternatives | doesn't fabricate trips |
| KB question with context | answers from KB (headers/bullets) | doesn't invent facts beyond KB |
| GoBus detail it doesn't have | says so + offers the hotline | doesn't guess |
| Complaint without details | asks "what happened?" first | doesn't open a ticket yet |
| Off-limits topic | refuses + pivots to travel help | no "educational/neutral" reframings |
| Hotline mentioned | bold **{hotline}** from `BotSettings` (single source) | no hardcoded number |
| Language | replies in the user's language (AR / EN) | — |

---

## 8. Two worked scenarios

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    Note over U,B: Scenario A — trip prices
    U->>B: "كام سعر رحلة القاهرة الغردقة elite؟"
    B->>B: rewrite places → intent=trips → SQL
    B-->>U: meta trips (table) + "إليك الرحلات من القاهرة إلى الغردقة:"

    Note over U,B: Scenario B — complaint (ask-first)
    U->>B: "I want to file a complaint about the driver"
    B-->>U: "Could you describe what happened…?"  (no form)
    U->>B: "he cursed at me"
    B-->>U: meta open_ticket_form (subject/details) → confirm
    U->>B: confirm
    B-->>U: "Ticket GB-2026-000003 created — email sent"
    U->>B: "What is the next trip to Dahab?"
    B-->>U: meta trips (table) — NO ticket form (no leak)
```

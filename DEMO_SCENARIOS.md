# GoBus Chatbot — Demo Scenarios

**30 English + 10 Arabic presentation questions** covering all KB content types:  
**Services · FAQ · About · Policies · Destinations · Stations · Trips**

Use a **new chat** before each demo block. Toggle language with **AR / EN** in the chat header.

**Chat:** http://localhost:5173/chat  
**Admin:** http://localhost:5173/login (credentials in `backend/.env`)

---

## Automated retrieval test

Run before a demo to confirm the backend loads the right context for each question:

```powershell
cd backend
.\venv\Scripts\python scripts\test_demo_scenarios.py
```

Expected: **35 passed, 0 failed** (30 English + 5 Arabic spot-checks).

---

## End-to-end chat test (live API + OpenAI)

Sends each question to `POST /api/chat/stream` and validates the assistant reply.

```powershell
cd backend
.\venv\Scripts\python scripts\test_chat_e2e.py
```

Results are written to **[CHAT_E2E_TEST_RESULTS.md](../CHAT_E2E_TEST_RESULTS.md)** (summary table + full replies).

**Latest run:** 25/30 passed — 5 trip questions failed because the model ignored trip data in context (retrieval OK). Re-run after prompt fixes.

---

## Content type coverage

| Type | What the bot loads | Example question |
|------|-------------------|------------------|
| **Services** | GoBus / GoMini / GoLemo KB articles | What is the difference between GoBus and GoMini? |
| **Stations** | Station name, hours, map URL | Nearest GoBus station in Nasr City? |
| **Trips** | Route, date, time, class, seats, price | Cairo – Alexandria trip schedules |
| **FAQ** | Booking, hotline, classes, schedules help | How can I book a GoBus ticket? |
| **About** | Company ownership, history | Who owns GoBus and when was it founded? |
| **Policies** | Cancellation, terms, changes | What is the cancellation and refund policy? |
| **Destinations** | Destination guides + KB articles | Tell me about Dahab |

---

## English scenarios — core (10)

| # | Question | Type | Status |
|---|----------|------|--------|
| 1 | What is the difference between GoBus and GoMini? | Services | ✅ |
| 2 | Nearest GoBus station in Nasr City? | Stations | ✅ |
| 3 | Cairo – Alexandria trip schedules | Trips | ✅ |
| 4 | What is the next trip to Dahab? | Trips | ✅ |
| 5 | How can I book a GoBus ticket? | FAQ | ✅ |
| 6 | Trip prices from Cairo to Hurghada | Trips | ✅ |
| 7 | Tell me about GoBus destinations | Destinations | ✅ |
| 8 | What is the GoBus hotline? | FAQ | ✅ |
| 9 | Seats available tomorrow to Sharm El Sheikh? | Trips | ✅ |
| 10 | What bus classes does GoBus offer? | FAQ | ✅ |

---

## English scenarios — extended (20)

| # | Question | Type | Status |
|---|----------|------|--------|
| 11 | Who owns GoBus and when was it founded? | About | ✅ |
| 12 | What is GoLemo and what services does it offer? | Services | ✅ |
| 13 | What is the cancellation and refund policy? | Policies | ✅ |
| 14 | Tell me about Hurghada as a destination | Destinations | ✅ |
| 15 | Where is the Giza station and what is the map link? | Stations | ✅ |
| 16 | Cairo to Marsa Alam schedule | Trips | ✅ |
| 17 | Are there open trips from Cairo to Port Said? | Trips | ✅ |
| 18 | How do I know trip schedules? | FAQ | ✅ |
| 19 | What destinations does GoBus serve? | Destinations | ✅ |
| 20 | Nearest GoBus station in Heliopolis? | Stations | ✅ |
| 21 | What is the price for Cairo to Alexandria elite class? | Trips | ✅ |
| 22 | Can I book tickets online? | FAQ | ✅ |
| 23 | Tell me about GoBus company history | About | ✅ |
| 24 | What are the terms and conditions? | Policies | ✅ |
| 25 | Tell me about Dahab | Destinations | ✅ |
| 26 | What is the difference between standard and elite? | FAQ | ✅ |
| 27 | Trip from Cairo to Luxor tomorrow | Trips | ✅ |
| 28 | Where is Madinaty station? | Stations | ✅ |
| 29 | What is GoMini? | Services | ✅ |
| 30 | Seats available on Cairo to Nuweiba trips? | Trips | ✅ |

---

## Arabic scenarios (10)

| # | Question | Type | Status |
|---|----------|------|--------|
| 1 | إيه الفرق بين GoBus و GoMini؟ | Services | ✅ |
| 2 | فين أقرب محطة في مدينة نصر؟ | Stations | ✅ |
| 3 | مواعيد رحلة القاهرة – الإسكندرية | Trips | ✅ |
| 4 | إيه أقرب رحلة من القاهرة لدهب؟ | Trips | — |
| 5 | كيف أحجز تذكرة GoBus؟ | FAQ | ✅ |
| 6 | كام سعر رحلة القاهرة الغردقة elite؟ | Trips | — |
| 7 | إيه الوجهات اللي GoBus بيروحها؟ | Destinations | — |
| 8 | إيه الخط الساخن؟ | FAQ | ✅ |
| 9 | هل في مقاعد فاضية بكرة على رحلة شرم الشيخ؟ | Trips | — |
| 10 | إيه الفرق بين standard و elite؟ | FAQ | — |

---

### Copy-paste — English (all 30)

```
What is the difference between GoBus and GoMini?
Nearest GoBus station in Nasr City?
Cairo – Alexandria trip schedules
What is the next trip to Dahab?
How can I book a GoBus ticket?
Trip prices from Cairo to Hurghada
Tell me about GoBus destinations
What is the GoBus hotline?
Seats available tomorrow to Sharm El Sheikh?
What bus classes does GoBus offer?
Who owns GoBus and when was it founded?
What is GoLemo and what services does it offer?
What is the cancellation and refund policy?
Tell me about Hurghada as a destination
Where is the Giza station and what is the map link?
Cairo to Marsa Alam schedule
Are there open trips from Cairo to Port Said?
How do I know trip schedules?
What destinations does GoBus serve?
Nearest GoBus station in Heliopolis?
What is the price for Cairo to Alexandria elite class?
Can I book tickets online?
Tell me about GoBus company history
What are the terms and conditions?
Tell me about Dahab
What is the difference between standard and elite?
Trip from Cairo to Luxor tomorrow
Where is Madinaty station?
What is GoMini?
Seats available on Cairo to Nuweiba trips?
```

### Copy-paste — Arabic

```
إيه الفرق بين GoBus و GoMini؟
فين أقرب محطة في مدينة نصر؟
مواعيد رحلة القاهرة – الإسكندرية
إيه أقرب رحلة من القاهرة لدهب؟
كيف أحجز تذكرة GoBus؟
كام سعر رحلة القاهرة الغردقة elite؟
إيه الوجهات اللي GoBus بيروحها؟
إيه الخط الساخن؟
هل في مقاعد فاضية بكرة على رحلة شرم الشيخ؟
إيه الفرق بين standard و elite؟
```

---

## Quick presentation flow (~8 min)

1. **Services + FAQ:** English #1 → #5 → #8  
2. **Trips:** English #3 → #4 → #16 → #6  
3. **Stations + Destinations:** English #2 → #15 → #25  
4. **About + Policies:** English #11 → #13 → #24  
5. **Arabic spot-check:** AR #1 → #3 → #5 → #8  
6. Show **Admin → Trips**, **Stations**, **Knowledge Base** tabs  

The core questions appear as **clickable chips** in the chat widget (language matches AR/EN toggle).

---

## Seeded dummy data (backend)

| Area | Details |
|------|---------|
| **Routes** | Cairo→Alexandria, Hurghada, Sharm, Dahab, Marsa Alam, Makadi, Nuweiba, North Coast, Luxor, Port Said, etc. |
| **Trips** | 14 days per route — times, seats, prices |
| **KB** | Services, FAQ, About, Policies, Destinations articles |
| **Stations** | Giza, Nasr City, Heliopolis, Madinaty, etc. with map URLs |

Restart the backend after code changes:

```powershell
cd backend
.\venv\Scripts\uvicorn app.main:app --reload --port 8000
```

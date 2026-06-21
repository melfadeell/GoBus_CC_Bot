# GoBus Chatbot — Features & Capabilities

Full-stack customer-service chatbot POC for GoBus: public streaming chat for customers and an admin panel to manage content, monitor usage, and tune the bot.

**Stack:** React 19 + TypeScript + Vite · FastAPI + MySQL · OpenAI GPT-4o

---

## Public Chat (`/chat`)

- Streaming AI replies (GPT-4o, token-by-token)
- Arabic & English UI (chat defaults to Arabic)
- Full-screen chat experience
- New chat / session persistence
- Demo question chips for quick testing
- Channel selector (WhatsApp, Instagram, LinkedIn, Facebook, TikTok, Website)
- Image upload for screenshots
- OCR on images (English + Arabic with DMS-style Arabic processing)
- Markdown-formatted bot replies
- Short conversation memory (last 5 user + 5 bot messages)
- Hybrid answers:
  - **GoBus-specific** → from knowledge base
  - **General questions** → general AI knowledge allowed
- Error handling + hotline fallback (19567)
- Stop / cancel streaming response

---

## AI & Bot Intelligence

- Knowledge base context injection per message
- Smart retrieval for:
  - KB articles
  - Stations
  - Destinations
  - Trips & routes
  - Services (GoBus, GoMini, GoLemo)
- Destination alias mapping (e.g. Alexandria → الإسكندرية)
- Booking / trip keyword detection
- Company / about inquiry detection (ownership, history, etc.)
- Service-specific rules (GoBus full data; GoMini / GoLemo limited)
- Configurable system prompt
- Configurable Arabic greeting
- Token usage tracking (prompt / completion / total per message)

---

## Admin Panel

### Authentication

- Admin login (JWT, **12-hour** expiry)
- Protected admin routes
- Auth success/failure logging to logs DB
- Logout

### Dashboard (`/admin`)

- Total conversations, messages, tokens
- KB articles, stations, destinations, active trips counts
- Channel filter
- Charts: daily token usage, messages trend, tokens by channel
- Fullscreen chart view

### Knowledge Base (`/admin/kb`)

- List / search articles by category
- Categories: Services, FAQ, About, Policies, Destinations
- Create / edit / delete articles
- Service scope (GoBus, GoMini, GoLemo, All)
- Active / inactive toggle
- Auto-generated slugs
- AI text enhance with compare modal (original vs enhanced)
- Import content from file (TXT, MD, CSV, PDF, images)
- OCR on imported images / PDF pages

### Stations (`/admin/stations`)

- List / search stations
- Create / edit / delete
- Name, description, city, map URL
- Working hours (including 24h)
- Active / inactive toggle

### Trips (`/admin/trips`) — demo data

- List trips with route, date, class, seats, price, status
- Create / edit / delete trips
- View trip details modal
- Routes: Cairo ↔ Alexandria, Hurghada, Sharm, Sokhna, Port Said, etc.
- Dummy trips seeded for ~14 days

### Destinations

- CRUD for destination guides (API + pages)
- Also available under KB Destinations tab

### Services

- GoBus, GoMini, GoLemo service definitions
- Synced into KB Services articles

### Conversations (`/admin/conversations`)

- View all chat sessions
- Read full message history per session
- Filter by date range (from / to)
- Filter by minimum message count
- Result count display

### Bot Settings (`/admin/bot-settings`)

- Edit Arabic greeting
- Edit system prompt
- AI enhance system prompt with instructions
- Compare original vs enhanced prompt
- Prompt version history
- Restore previous prompt versions

### Operational Metrics (`/admin/metrics`)

- Separate MySQL logs database (`gobus_chatbot_logs`)
- Overview: API requests, chat turns, LLM calls, errors, rate-limit hits (429), avg latency, tokens
- Tabs: API requests, chat logs, LLM calls, auth logs, error logs
- Date range filter (7 / 30 days)
- Recharts overview charts (requests, chat, tokens, errors)

---

## Admin UX

- Collapsible sidebar (saved in localStorage)
- GoBus orange branding (`#F7941D`)
- Separate languages: admin (English default) vs chat (Arabic default)
- RTL / LTR support
- Mobile-friendly admin layout
- “Try Chat” link from admin
- Loading, empty, and error states
- Success banners on save

---

## OCR & File Processing

- Chat image OCR endpoint
- KB file extraction endpoint
- Tesseract English (`eng`)
- Tesseract Arabic (`ara`) + ArabicTextProcessor (RTL, ligatures, phunspell)
- PDF text extraction (PyMuPDF) with OCR fallback on scanned pages
- Image prep (resize, EXIF fix) before OCR

---

## Data & Seeding

- Auto-create MySQL databases on first run (`gobus_chatbot` + `gobus_chatbot_logs`)
- Auto-create tables + lightweight migrations
- Seed from `Website data/`:
  - About pages
  - FAQ
  - Policies
  - Contact
  - 10 destination guides
  - Stations JSON
- Seed demo trips & routes
- Seed demo chat sessions with token data for dashboard
- Company overview KB article for ownership / general inquiries

---

## API Capabilities

| API Area        | Endpoints |
|-----------------|-----------|
| Auth            | Login, me |
| Chat            | Stream, OCR |
| KB              | CRUD, categories, enhance, extract-file |
| Stations        | CRUD |
| Destinations    | CRUD |
| Trips           | CRUD, routes |
| Services        | List, get, update |
| Conversations   | List (filtered), messages |
| Dashboard       | Stats, analytics |
| Metrics         | Overview, charts, paginated logs (requests, chat, LLM, auth, errors) |
| Bot Settings    | Get/update, prompt enhance, versions, restore, public greeting |
| Health          | `/api/health` |

- OpenAPI docs at `http://localhost:8000/docs`
- CORS configured for local frontend
- SSE streaming for chat
- **Rate limit:** 15 chat stream messages per minute per IP (in-memory; single-server POC)
- HTTP request logging middleware for all `/api/*` routes
- Chat / LLM / auth / error logging to separate logs DB

---

## What the Bot Can Answer (Examples)

- Station locations & hours
- Destination info (Alexandria, Dahab, Hurghada, etc.)
- Trip schedules, prices, seats (demo data)
- Booking FAQ
- GoBus vs GoMini vs GoLemo differences
- Company about / ownership info
- Hotline & contact info
- General questions (geography, definitions, etc.)
- Screenshot / booking error help (via OCR text)

---

## Current Limitations

- Channels are labels only (no live WhatsApp / Instagram integration)
- Trips are dummy data, not a live booking system
- Keyword-based KB search (no vector / semantic search)
- Single admin user, no roles
- In-memory rate limiting (not distributed across instances)
- No automated tests
- No production deployment setup in this repo

---

## URLs

| URL | Description |
|-----|-------------|
| `/chat` | Public streaming chat |
| `/login` | Admin login |
| `/admin` | Dashboard |
| `/admin/kb` | Knowledge base |
| `/admin/stations` | Stations |
| `/admin/trips` | Trips |
| `/admin/conversations` | Chat logs |
| `/admin/metrics` | Operational metrics (logs DB) |
| `/admin/bot-settings` | Bot prompt & greeting |

**Default admin:** `admin@gobus.local` / `admin123` (change in `backend/.env` before production)

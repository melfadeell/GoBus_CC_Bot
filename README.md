# GoBus Omnichannel Chatbot

React + FastAPI + MySQL chatbot for GoBus customer service with streaming GPT-4o, editable knowledge base, stations, destinations, and dummy trip data.

## Prerequisites

- Python 3.11+
- Node.js 20+
- MySQL server running (phpMyAdmin optional — DB is auto-created on first start)

## Setup

### 1. MySQL

Ensure MySQL is running. The app **creates the database automatically** on first startup if it does not exist.

You only need a MySQL user with permission to create databases (default `root` with no password works locally).

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env`:

- `DATABASE_URL` — your MySQL connection string (database name is created automatically if missing)
- `OPENAI_API_KEY` — your OpenAI key
- `OPENAI_MODEL=gpt-4o`

Start the API (creates DB + tables + seeds data automatically on **first run**):

```bash
uvicorn app.main:app --reload --port 8000
```

Optional manual re-seed (only runs when admin account does not exist):

```bash
python -m app.seed.seed_website_data
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Default Admin Login

- Email: `admin@gobus.local`
- Password: `admin123`

Change these in `backend/.env` before production.

## URLs

| URL | Description |
|-----|-------------|
| `/chat` | Public streaming chat (client demo) |
| `/login` | Admin login |
| `/admin` | Dashboard |
| `/admin/kb` | Knowledge base CRUD |
| `/admin/stations` | Stations CRUD |
| `/admin/destinations` | Destinations CRUD |
| `/admin/trips` | Trips & seats (dummy data) |
| `/admin/services` | GoBus / GoMini / GoLemo |
| `/admin/bot-settings` | Bot prompt & hotline |
| `/admin/conversations` | Chat logs |

## Demo Questions

- `فين أقرب محطة ليا في مدينة نصر؟`
- `عايز أحجز القاهرة اسكندرية بكرة`
- `إيه الفرق بين gobus و gomini؟`
- `What is GoBus hotline?`
- `Tell me about Alexandria destination`

## Services Rules

- **GoBus**: full KB, stations, trips, destinations
- **GoMini / GoLemo**: general service info only; bot declines detailed questions
- **Hotline**: 19567

## Data Sources

Imported from `Website data/`:

- About pages, FAQ, policies, contact
- 10 destination city guides
- Stations JSON (`محطات وموانئ جوباص.json`)
- Dummy trips seeded for 14 days on 5 routes

## API Docs

http://localhost:8000/docs

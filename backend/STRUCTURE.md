# Backend layout

```
backend/app/
├── core/           # Constants, exception handlers
├── models/         # SQLAlchemy ORM models
├── schemas/        # Pydantic request/response models
├── routers/        # FastAPI route handlers (thin)
├── services/       # Business logic (chat, KB retrieval, AI)
├── utils/          # Text helpers, shared utilities
├── seed/           # Database seed from Website data
├── auth.py         # JWT + password hashing
├── config.py       # Environment settings
├── database.py     # Engine + session factory
└── main.py         # App entry point
```

Routers delegate to services. Chat streaming uses a dedicated DB session per request.

On startup, `app/core/bootstrap.py` creates the MySQL database (if missing), tables, and seeds initial data on first run.

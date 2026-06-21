# Frontend layout

```
frontend/src/
├── api/            # HTTP client + types
├── components/
│   ├── admin/      # Shared admin UI (tables, forms, states)
│   ├── chat/       # Chat widget + message bubbles
│   └── layout/     # Admin shell (sidebar, header)
├── hooks/          # useChatStream, useDebounce
├── pages/          # Route-level screens
├── theme/          # GoBus design tokens
├── App.tsx         # Router
└── main.tsx        # Entry
```

Public chat: `/chat` · Admin: `/admin/*` · Login: `/login`

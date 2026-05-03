# Vaaksetu

Real-time voice AI call assistant — full-stack application.

## Project Structure

```
vaaksetu/
├── backend/                    # FastAPI (Python)
│   ├── app/
│   │   ├── main.py             # FastAPI entry point
│   │   ├── config.py           # Environment-based configuration
│   │   ├── models.py           # Pydantic models (shared contract)
│   │   ├── websockets/         # WebSocket connection management
│   │   │   └── connection.py
│   │   └── services/           # Business logic layer
│   │       └── call_service.py
│   ├── requirements.txt
│   ├── .env                    # API keys (git-ignored)
│   └── .env.example
│
├── frontend/                   # Vite + React + TypeScript
│   ├── src/
│   │   ├── components/ui/      # Shadcn UI components
│   │   ├── lib/utils.ts        # Tailwind merge utility
│   │   ├── types/              # Shared TypeScript interfaces
│   │   │   └── call-metadata.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── .env                    # Frontend env vars (git-ignored)
│   └── .env.example
│
└── README.md
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Adding Shadcn Components

```bash
cd frontend
npx shadcn@latest add button card dialog   # etc.
```

## Shared Models

The `CallMetadata` interface is defined in both:
- **Backend**: `backend/app/models.py` (Pydantic)
- **Frontend**: `frontend/src/types/call-metadata.ts` (TypeScript)

Keep these in sync when making changes.

## Environment Variables

All API keys and secrets are loaded from `.env` files (never committed).
Copy `.env.example → .env` in both `backend/` and `frontend/` directories.

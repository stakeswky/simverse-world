# Skills World — 赛博永生开放世界

## Quick Start (Development)

### Prerequisites
- Docker + Docker Compose
- Python 3.11+
- Node.js 18+

### 1. Start infrastructure

```bash
docker compose up -d
```

### 2. Backend

```bash
cd backend
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
pip install -e ".[dev]"
alembic upgrade head
python -m seed.seed_residents
uvicorn app.main:app --reload
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open http://localhost:5173

## Architecture

- **Frontend:** React 18 + Vite + TypeScript + Phaser.js 3.80
- **Backend:** FastAPI + SQLAlchemy async + Alembic
- **Database:** PostgreSQL 16
- **Cache:** Redis 7
- **LLM:** Anthropic Claude (Haiku default)

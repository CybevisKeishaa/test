# Fabbi Todo App — Developer Assessment Codebase

A full-stack Todo application built with JWT authentication, designed for developer skill evaluation.

## Tech Stack

### Backend

- **FastAPI** — Python async web framework
- **PostgreSQL** — Relational database
- **Redis** — Caching layer
- **SQLAlchemy 2.0** — Async ORM
- **Alembic** — Database migrations
- **Pydantic v2** — Data validation

### Frontend

- **React 19** + **TypeScript** — UI framework
- **Vite** — Build tool
- **Tailwind CSS v4** — Utility-first CSS
- **shadcn/ui** — Component library
- **TanStack React Query** — Server state management
- **react-hook-form** + **Zod** — Form handling & validation
- **React Router** — Client-side routing

### Infrastructure

- **Docker Compose** — Container orchestration
- **Dockerized** backend + frontend + PostgreSQL + Redis

## Getting Started

### Prerequisites

- Docker & Docker Compose installed
- Git

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd fabbi

# Copy environment variables
cp .env.example .env

# Start all services
docker compose up -d --build

# Seed the database with a demo user and sample TODOs
docker compose exec backend python -m app.db.seed
```

All four services have healthchecks, and the backend waits for Postgres and
Redis to report healthy before it runs migrations, so a cold `up` no longer
races the database.

If a default port is already taken on your machine, override it without
editing the compose file (shell variables win over `.env`):

```bash
REDIS_PORT=6380 POSTGRES_PORT=55432 docker compose up -d --build
```

The application will be available at:

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Demo Login credentials**:
  - Email: `demo@test.com`
  - Password: `Demo@123`

By default the seed command creates 100 users and 1,000 TODOs so the assessment is quick to set up. To test performance with a larger dataset, pass seed variables explicitly:

```bash
docker compose exec -e SEED_USERS=10000 -e SEED_TODOS=1000000 backend python -m app.db.seed
```

### Local Development (without Docker)

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate.bat
pip install -r requirements.txt

# Start PostgreSQL and Redis locally, then run migrations and seed data:
alembic upgrade head
python -m app.db.seed

# Start backend server
uvicorn app.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Production configuration

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production overlay keeps Postgres and Redis off the host network, drops
every `:-default`, and runs uvicorn with 4 workers. It therefore refuses to
start until the real secrets are in the environment:

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
export REDIS_PASSWORD=...
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export CORS_ORIGINS=https://todo.example.com
export VITE_API_URL=https://api.example.com
```

The app also refuses to boot with `ENVIRONMENT=production` while `JWT_SECRET`
is still the value shipped in `.env.example`.

## API Endpoints

### Authentication

| Method | Endpoint                | Description           |
| ------ | ----------------------- | --------------------- |
| POST   | `/api/v1/auth/register` | Register a new user   |
| POST   | `/api/v1/auth/login`    | Login and get tokens  |
| POST   | `/api/v1/auth/refresh`  | Refresh access token  |
| POST   | `/api/v1/auth/logout`   | Logout user           |
| GET    | `/api/v1/auth/me`       | Get current user info |

### Todos

| Method | Endpoint             | Description            |
| ------ | -------------------- | ---------------------- |
| GET    | `/api/v1/todos`      | List todos (paginated) |
| POST   | `/api/v1/todos`      | Create a new todo      |
| GET    | `/api/v1/todos/{id}` | Get a specific todo    |
| PUT    | `/api/v1/todos/{id}` | Update a todo          |
| DELETE | `/api/v1/todos/{id}` | Delete a todo          |

## Documentation

| Document | Contents |
|---|---|
| [`docs/TODO_SHARING_SPEC.md`](docs/TODO_SHARING_SPEC.md) | Technical specification for todo list sharing |
| [`docs/MANUAL_TEST_PLAN.md`](docs/MANUAL_TEST_PLAN.md) | Manual test plan and execution results |
| [`docs/DB_PERFORMANCE.md`](docs/DB_PERFORMANCE.md) | Index analysis, `EXPLAIN ANALYZE` output, benchmarks |
| [`docs/AI_USAGE.md`](docs/AI_USAGE.md) | Disclosure of AI assistance |

## Project Structure

```
fabbi/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API route handlers
│   │   ├── core/            # Config, security, Redis
│   │   ├── db/              # Database setup
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic validation
│   │   ├── services/        # Business logic
│   │   └── main.py          # FastAPI app
│   ├── alembic/             # DB migrations
│   └── tests/               # Test suite
├── frontend/
│   ├── nginx.conf           # SPA fallback + caching for the runtime image
│   └── src/
│       ├── components/ui/   # shadcn/ui components
│       ├── features/        # Feature modules (auth, todos)
│       ├── lib/             # Utilities (API, query client)
│       ├── pages/           # Route pages
│       └── router/          # React Router config
├── e2e/                     # Playwright end-to-end suite
├── docs/                    # Spec, test plan, performance report
├── docker-compose.yml       # Development stack
└── docker-compose.prod.yml  # Production overrides
```

## Running Tests

### Backend Automated Tests
```bash
cd backend
pytest tests/ -v
```

### Frontend E2E Tests (Playwright)

The suite lives in `e2e/` and runs against a stack that is already up.

```bash
docker compose up -d --build          # from the repo root

cd e2e
npm install
npx playwright install chromium       # first run only
npx playwright test                   # headless
npx playwright test --headed          # watch it drive the browser
npx playwright test --ui              # interactive runner
npx playwright show-report            # last HTML report
```

Point it somewhere else with `E2E_BASE_URL` and `E2E_API_URL`, for example
against the Vite dev server:

```bash
E2E_BASE_URL=http://localhost:5173 npx playwright test
```

### Database Performance Benchmarking
To test database indexing and query execution times with 1 million records:
```bash
docker compose exec -e SEED_USERS=10000 -e SEED_TODOS=1000000 backend python -m app.db.seed
```
Connect to the PostgreSQL container to run `EXPLAIN ANALYZE`:
```bash
docker compose exec postgres psql -U fabbi -d postgres
```

Measured before/after numbers and the indexing rationale are in
[`docs/DB_PERFORMANCE.md`](docs/DB_PERFORMANCE.md).


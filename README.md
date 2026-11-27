# AIProject

A full-stack AI/ML platform with role-based access control, built with **FastAPI**,
**PostgreSQL** and **React**. It covers dataset management, model training and prediction,
MLOps monitoring, an employee directory and local LLM chat through **Ollama**.

**Live demo:** [aiml-project-ecru.vercel.app](https://aiml-project-ecru.vercel.app) ·
**API docs:** [aiml-backend-yrj8.onrender.com/docs](https://aiml-backend-yrj8.onrender.com/docs)

---

## Features

- **Authentication** — JWT access and refresh tokens, Argon2id password hashing, automatic
  session revocation on password or role changes.
- **Role-based access control** — three roles (User, Admin, Super Admin), enforced by the backend
  on every endpoint.
- **Employee management** — create, edit, search and filter employee records; sensitive fields
  are visible only to authorised roles.
- **Datasets and ML** — CSV/Excel upload with validation, scikit-learn training (classification
  and regression), model versioning and predictions.
- **MLOps** — experiments, background jobs, deployments, monitoring, data-drift detection and
  explainability (SHAP, LIME).
- **Local AI** — LLM chat and text analysis with Ollama (`llama3.2:3b`); no external API keys.
- **Administration** — audit log of sensitive actions and global settings (sign-up control,
  maintenance mode, announcements).

## Roles and permissions

| Capability | User | Admin | Super Admin |
|---|:-:|:-:|:-:|
| View employees, datasets, models and reports | ✅ | ✅ | ✅ |
| View employee salary and phone | — | ✅ | ✅ |
| Create and edit employees | — | ✅ | ✅ |
| Delete employees | — | Own records | All records |
| Upload data, train models, run predictions | — | ✅ | ✅ |
| Deploy models | — | — | ✅ |
| Manage user accounts | — | User accounts | All accounts and roles |
| View audit log | — | Employee and ML events | All events |
| Change global settings | — | — | ✅ |

- Any number of **User** accounts can be created through sign-up.
- The **Admin** and **Super Admin** accounts can each be registered through sign-up **only once**;
  afterwards only a Super Admin can grant these roles.
- Users cannot change their own role, and the last active Super Admin cannot be removed.

## Tech stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Machine learning | NumPy, pandas, scikit-learn, SHAP, LIME, Matplotlib, seaborn |
| AI (optional) | Ollama, PyTorch, Transformers, Sentence Transformers, LangChain, LangGraph |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Testing | pytest, Vitest, Ruff |
| Deployment | Docker, Render, Vercel, GitHub Actions |

## Architecture

```
React frontend  ──HTTPS──▶  FastAPI backend  ──▶  PostgreSQL
                               │
                               ├── Routes → permission check → services → repositories
                               ├── ML pipeline (scikit-learn)
                               └── AI services (Ollama, Transformers)
```

## Project structure

```
app/
  api/            API routes and dependencies
  core/           configuration, permissions, security, middleware
  database/       SQLAlchemy models and session
  repositories/   data access layer
  services/       business logic
  ml/             data processing, training, prediction
  ai/             LLM chat, embeddings, classification
  schemas/        request and response models
alembic/          database migrations
frontend/         React application
scripts/          utility scripts (admin setup, backups, smoke tests)
tests/            unit and integration tests
notebooks/        exploratory notebooks
datasets/         sample datasets
```

## Getting started

### Prerequisites

Python 3.12+, PostgreSQL, Node.js 22. Optional: Ollama (LLM chat), Docker.

### Backend

```bash
git clone https://github.com/Mehak-991/AI-ML-Project-.git
cd AI-ML-Project-

python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env              # then set DATABASE_URL and JWT_SECRET_KEY
alembic upgrade head
python main.py                    # http://127.0.0.1:8000/docs
```

Optional packages:

```bash
pip install -r requirements-llm.txt        # LangChain, LangGraph, LlamaIndex
pip install -r requirements-notebook.txt   # Jupyter
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-nlp.txt        # Transformers, Sentence Transformers
```

### Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

### First accounts

Open the app, choose **Sign In → Create an Account**, and register the **Super Admin** and
**Admin** accounts. Alternatively, from the command line:

```bash
python scripts/create_super_admin.py --email admin@example.com --role super_admin
```

### LLM chat (optional)

Install [Ollama](https://ollama.com) and pull the model:

```bash
ollama pull llama3.2:3b
```

## Configuration

Settings are read from environment variables or a `.env` file. See
[.env.example](.env.example) for the full list.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Token signing key (at least 32 bytes) |
| `APP_ENV` | `development`, `testing` or `production` |
| `CORS_ORIGINS` | Allowed frontend URLs |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Ollama server and model |
| `VITE_API_BASE_URL` | Backend URL for a separately hosted frontend |

## API

All endpoints are under `/api/v1`. Interactive documentation is available at `/docs`.
Protected endpoints require an `Authorization: Bearer <token>` header obtained from
`POST /api/v1/auth/login`.

| Area | Main endpoints |
|---|---|
| Authentication | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me` |
| Users | `/auth/users` |
| Employees | `/employees` |
| Datasets | `/datasets` |
| Models | `/models`, `/models/train`, `/models/{id}/predict` |
| Monitoring | `/monitoring`, `/drift`, `/deployments`, `/predictions/history` |
| Experiments and jobs | `/experiments`, `/jobs` |
| AI | `/llm/chat`, `/nlp/analyze`, `/embeddings` |
| Administration | `/audit-logs`, `/settings` |
| Health | `/health`, `/api/v1/health` |

## Testing

```bash
pytest                    # backend tests
cd frontend && npm test   # frontend tests
ruff check .              # linting
```

End-to-end check against a running server:

```bash
SMOKE_EMAIL=<admin-email> SMOKE_PASSWORD=<password> python scripts/smoke_test.py <backend-url>
```

## Deployment

| Component | Platform | Configuration |
|---|---|---|
| Backend and database | Render | [render.yaml](render.yaml) |
| Frontend | Vercel | [frontend/vercel.json](frontend/vercel.json) |

**Backend (Render):** create a Blueprint from this repository. Render provisions the backend and
PostgreSQL, generates secrets and runs migrations on startup. Set `CORS_ORIGINS` to the frontend
URL.

**Frontend (Vercel):**

```bash
cd frontend
vercel env add VITE_API_BASE_URL production   # https://<backend-url>/api/v1
vercel deploy --prod
```

**Self-hosted (Docker):**

```bash
cp .env.example .env
docker compose up -d --build
```

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for backups, HTTPS and production checklists.

## Security

- Permissions are checked on the server for every request; roles are read from the database.
- Passwords are hashed with Argon2id; sessions are revoked when credentials or roles change.
- Input validation, rate limiting, request size limits, CORS restrictions and security headers.
- Sensitive actions are recorded in the audit log.
- Secrets are supplied through environment variables and never committed.

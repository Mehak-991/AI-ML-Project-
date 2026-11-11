# AI/ML Project

A minimal Python AI/ML development environment with FastAPI, SQLAlchemy, Ollama local LLM integration, and common ML/Deep Learning libraries.

---

## Requirements

- Python 3.12+
- (Optional) PostgreSQL — SQLite works out of the box with no server
- (Optional) [Ollama](https://ollama.com) — for local LLM inference

---

## Project Structure

```
AIProject/
│
├── app/
│   ├── api/            # API route placeholders
│   ├── models/         # ORM model placeholders
│   ├── services/       # Service layer (includes ollama_service.py)
│   ├── repository/     # Repository layer placeholders
│   ├── database/       # SQLAlchemy engine & session (database.py)
│   ├── schemas/        # Pydantic schema placeholders
│   ├── utils/          # Utility placeholders
│   └── main.py         # FastAPI application entry point
│
├── datasets/           # Place your datasets here
├── notebooks/          # Jupyter notebooks
├── uploads/            # File uploads
├── trained_models/     # Saved model artifacts
├── tests/              # Test suite
├── logs/               # Application logs
│
├── .env.example        # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Create a virtual environment

```bash
python -m venv venv
```

### 2. Activate the virtual environment

**Windows:**
```powershell
venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. Upgrade pip

```bash
python -m pip install --upgrade pip
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `torch`, `torchvision`, and `torchaudio` above install the CPU build by default.
> For GPU support visit <https://pytorch.org/get-started/locally/> and install
> the correct build for your hardware before running `pip install -r requirements.txt`.

### 5. Configure environment variables

```bash
cp .env.example .env
# Edit .env to match your setup
```

---

## Run the API

```bash
uvicorn app.main:app --reload
```

- API root: <http://127.0.0.1:8000/>
- Swagger UI: <http://127.0.0.1:8000/docs>

---

## Database

### SQLite (default — no server required)

The default `DATABASE_URL` in `.env.example` is:

```
DATABASE_URL=sqlite:///./aiml.db
```

No extra setup needed. The file is created automatically on first run.

### PostgreSQL

1. Create a database: `createdb aimldb`
2. Set in `.env`:

```
DATABASE_URL=postgresql://postgres:password@localhost:5432/aimldb
```

---

## Ollama (local LLM)

Ollama lets you run large language models locally without an API key or internet connection.

### Install Ollama

Download from <https://ollama.com> and follow the platform instructions.

### Pull a model

```bash
ollama pull llama3.2:3b
```

### Configure

Set in `.env`:

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

### Verify connectivity

```python
from app.services.ollama_service import check_ollama_connection
print(check_ollama_connection())
```

---

## Run Tests

```bash
pytest tests/ -v
```

Tests 8 and 9 (Ollama) are **automatically skipped** when the local Ollama service
is not running.  Test 7 (PostgreSQL) is skipped when `TEST_DATABASE_URL` is not set.

---

## Dependencies Overview

| Group | Packages |
|---|---|
| Data science | numpy, pandas, matplotlib, seaborn, scikit-learn, openpyxl |
| Notebooks | notebook, jupyter, ipykernel |
| Deep learning | torch, torchvision, torchaudio, tensorflow, transformers, sentence-transformers, datasets, evaluate |
| LLM / Agents | ollama, langchain, langgraph, llama-index, tiktoken |
| API & DB | fastapi, uvicorn, sqlalchemy, alembic, pydantic, python-multipart, psycopg[binary] |
| Utilities | python-dotenv, httpx |

> **No OpenAI dependency.** This project uses Ollama for all local LLM functionality.

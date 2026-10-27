# AIProject

Modular, production-oriented AI/ML platform:

- **Part 1:** FastAPI REST API, typed configuration, error handling, health checks, tests, linting
- **Part 2:** PostgreSQL data layer (SQLAlchemy 2.x + Alembic), CSV/Excel ingestion and
  validation, data profiling, and a leakage-safe scikit-learn training → persistence → prediction
  pipeline exposed through versioned API endpoints
- **Part 3 (current):** optional AI services: Sentence Transformers embeddings, transformer
  sentiment classification, OpenAI chat completion, token counting, and a LangGraph long-text
  analysis workflow. All of them are behind optional dependency groups, so the core API runs
  without them.

A full RAG system comes in a later phase.

## Project layout

```
app/
  ai/                AI services; optional packages are imported lazily:
                       container (per-app DI), optional (lazy imports), runtime (device,
                       timeouts), model_cache, tokens, embeddings, transformer_inference,
                       classification, llm (OpenAI), text_splitting (LangChain),
                       workflows/text_analysis (LangGraph)
  api/routes/        root, health, datasets, models, ai; api/router.py aggregates v1
  api/deps.py        Shared dependencies (settings, DB session, AI services)
  core/              config.py (settings), exceptions.py, error_handlers.py
  database/          base.py, session.py (engine/session/diagnostics), types.py, models/
  ml/                Framework-free data & ML code:
                       ingestion, validation, profiling, preprocessing, training,
                       persistence, prediction, synthetic, visualization
  repositories/      Data access (datasets, ml_models)
  schemas/           Pydantic request/response models
  services/          Use cases (dataset_service, model_service, storage, health_service)
  utils/             Logging, safe path handling
  main.py            App factory `create_app()` and ASGI `app`
alembic/versions/    Migrations (0001: datasets + ml_models)
datasets/examples/   Seeded synthetic demo CSVs (committed)
scripts/             check_health, check_db, generate_synthetic_data, profile_dataset, train_model,
                     download_models, nlp_demo, evaluate_classifier
tests/unit/          Fast tests (SQLite test double, no external services)
tests/integration/   PostgreSQL tests — run only when TEST_DATABASE_URL is set
uploads/ trained_models/ logs/ reports/   Runtime data (git-ignored)
```

## Prerequisites

- Python **3.12+** (`python --version`; on Windows, `py -0` lists installed versions)
- Git
- PostgreSQL 14+ — needed for the dataset/model endpoints and required when
  `APP_ENV=production`. Not needed to run the unit tests.

## Setup — Windows PowerShell

```powershell
cd "C:\path\to\AIProject"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

If activation fails with *"running scripts is disabled on this system"*, run once:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

## Setup — Linux / macOS

```bash
cd /path/to/AIProject
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
```

## Dependencies

| Group | Install | Contents |
|---|---|---|
| Runtime | `pip install -r requirements.txt` | FastAPI, Uvicorn, python-multipart, Pydantic, pydantic-settings, python-dotenv, SQLAlchemy, psycopg, Alembic, NumPy, pandas, scikit-learn, joblib, openpyxl, Matplotlib, seaborn |
| Dev & test | `pip install -r requirements-dev.txt` | Runtime + pytest, pytest-cov, HTTPX, Ruff |
| `torch` | see [AI setup](#ai-services-part-3) | PyTorch ≥2.4, torchvision. Install from the index for your hardware |
| `nlp` | `pip install -e ".[nlp]"` or `-r requirements-nlp.txt` | transformers (v4 or v5), sentence-transformers, datasets, evaluate. Needs `torch` |
| `llm` | `pip install -e ".[llm]"` | openai (2.x or 3.x), tiktoken |
| `agents` | `pip install -e ".[agents]"` | langgraph, langchain-core, langchain-text-splitters |
| `rag` | `pip install -e ".[rag]"` | llama-index-core. Reserved for Part 4; no code uses it yet |
| `ai` | `pip install -e ".[ai]"` | nlp + llm + agents (install torch first) |

`requirements-llm.txt` (llm + agents, no PyTorch) and `requirements-nlp.txt` mirror these groups
for pip-only workflows. The core runtime has no AI or GPU dependencies.

## PostgreSQL setup

1. Install PostgreSQL (Windows installer from postgresql.org, `brew install postgresql`, or
   `sudo apt install postgresql`), or run it in Docker:
   ```bash
   docker run -d --name aiproject-db -p 5432:5432 \
     -e POSTGRES_USER=aiproject -e POSTGRES_PASSWORD=<choose-a-password> -e POSTGRES_DB=aiproject \
     postgres:17
   ```
2. Create a role and databases (skip if you used the Docker command above). In `psql` as a superuser:
   ```sql
   CREATE ROLE aiproject LOGIN PASSWORD '<choose-a-password>';
   CREATE DATABASE aiproject OWNER aiproject;
   CREATE DATABASE aiproject_test OWNER aiproject;  -- disposable, for integration tests
   ```
3. Put the URL in `.env` (never commit it):
   ```
   DATABASE_URL=postgresql+psycopg://aiproject:<password>@localhost:5432/aiproject
   ```
   Plain `postgresql://` URLs are rewritten to the psycopg 3 driver automatically.
   URL-encode special characters in the password (e.g. `@` → `%40`).
4. Check connectivity and apply migrations:
   ```bash
   python scripts/check_db.py     # prints status, server version, tables; never the password
   alembic upgrade head
   ```

`check_db.py` and `/api/v1/health` classify failures (`authentication_failed`,
`database_not_found`, `connection_refused`, `host_not_found`, `timeout`, `driver_missing`)
and print a hint for each. The API never switches to SQLite on its own. In production a
non-PostgreSQL `DATABASE_URL` is rejected at startup. Without `DATABASE_URL`, the
dataset/model endpoints return **503 `database_not_configured`** while the health
endpoints keep working.

### Migrations

```bash
alembic upgrade head                                   # apply
alembic downgrade -1                                   # roll back one
alembic revision --autogenerate -m "describe change"   # after changing models
alembic upgrade head --sql                             # print SQL without running it
```

Register new model modules in [app/database/models/\_\_init\_\_.py](app/database/models/__init__.py)
so autogenerate can see them.

## Configuration

Settings come from environment variables first, then `.env`
([app/core/config.py](app/core/config.py)).

| Variable | Default | Notes |
|---|---|---|
| `APP_NAME` | `AIProject` | |
| `APP_ENV` | `development` | `development`, `testing` or `production` |
| `DEBUG` | `false` | Must be `false` in production |
| `API_V1_PREFIX` | `/api/v1` | |
| `LOG_LEVEL` | `INFO` | |
| `CORS_ORIGINS` | localhost:3000 in dev, none in prod | Comma-separated; `*` rejected in production |
| `DATABASE_URL` | unset | Required (PostgreSQL) in production |
| `DATABASE_CONNECT_TIMEOUT` / `_POOL_SIZE` / `_MAX_OVERFLOW` / `_ECHO` | `5` / `5` / `10` / `false` | |
| `UPLOAD_DIR` / `MODEL_DIR` | `uploads` / `trained_models` | Server-side only; never taken from requests |
| `MAX_UPLOAD_SIZE_MB` | `25` | Enforced while streaming |
| `MAX_DATASET_ROWS` / `MAX_DATASET_COLUMNS` | `200000` / `500` | |
| `MAX_PREDICTION_RECORDS` | `1000` | Per request |
| `OPENAI_API_KEY` | unset | Later phases |

Invalid settings stop startup with a `ConfigurationError` that lists each problem without
echoing secrets.

## Running the application

```bash
uvicorn app.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs · ReDoc: http://127.0.0.1:8000/redoc

| Method & path | Purpose |
|---|---|
| `GET /` | Welcome |
| `GET /health` | Liveness (no dependency checks) |
| `GET /api/v1/health` | Readiness incl. database; 503 if a configured DB is down |
| `POST /api/v1/datasets/validate` | Validate + summarize an uploaded file **without storing it** |
| `POST /api/v1/datasets` | Upload and register a dataset (201) |
| `GET /api/v1/datasets` · `GET /api/v1/datasets/{id}` | List / get dataset metadata |
| `GET /api/v1/datasets/{id}/summary?target_column=` | Validation report + profile of a stored dataset |
| `POST /api/v1/models/train` | Train a baseline model on a stored dataset (201) |
| `GET /api/v1/models[?dataset_id=]` · `GET /api/v1/models/{id}` | Model metadata, feature schema, metrics |
| `POST /api/v1/models/{id}/predict` | Predict with a saved model |

All errors use one envelope: `{"error": {"code": "...", "message": "...", "details": ...}}`.
Upload errors: 415 `unsupported_file_type`, 413 `file_too_large`, 400 `invalid_file`,
422 `data_validation_error`. Training: 422 `training_error`. Missing IDs: 404 `not_found`.

## Training-to-prediction workflow

Requires a configured PostgreSQL database with migrations applied (see above).

**1. Generate the demo data** (already committed in `datasets/examples/`; this re-creates it):
```bash
python scripts/generate_synthetic_data.py
```
These are synthetic, seeded datasets with generic columns (`num_a`, `num_b`, `num_c`,
`cat_a`, `cat_b`) and a `label` (yes/no) or `value` (continuous) target. A few missing
values and duplicate rows are injected on purpose. They are not real data.

**2. Start the server** with `uvicorn app.main:app --reload`, then in a second terminal:

PowerShell (uses `curl.exe`, not the `curl` alias):
```powershell
$base = "http://127.0.0.1:8000/api/v1"
# Optional: validate without storing
curl.exe -s -F "file=@datasets/examples/synthetic_classification.csv" -F "target_column=label" "$base/datasets/validate"
# Upload
$ds = curl.exe -s -F "file=@datasets/examples/synthetic_classification.csv" -F "name=demo" "$base/datasets" | ConvertFrom-Json
$dsId = $ds.dataset.id
# Train
$body = @{ dataset_id = $dsId; target_column = "label"; algorithm = "linear" } | ConvertTo-Json
$model = Invoke-RestMethod -Method Post -Uri "$base/models/train" -ContentType "application/json" -Body $body
$model.metrics.test
# Predict
$records = @{ records = @(@{ num_a = 55.2; num_b = 0.7; num_c = 4; cat_a = "red"; cat_b = "small" }) } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$base/models/$($model.id)/predict" -ContentType "application/json" -Body $records
```

bash:
```bash
BASE=http://127.0.0.1:8000/api/v1
DS_ID=$(curl -s -F "file=@datasets/examples/synthetic_classification.csv" -F "name=demo" \
  $BASE/datasets | python -c "import sys,json; print(json.load(sys.stdin)['dataset']['id'])")
MODEL_ID=$(curl -s -X POST $BASE/models/train -H "Content-Type: application/json" \
  -d "{\"dataset_id\": \"$DS_ID\", \"target_column\": \"label\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -s $BASE/models/$MODEL_ID
curl -s -X POST $BASE/models/$MODEL_ID/predict -H "Content-Type: application/json" \
  -d '{"records": [{"num_a": 55.2, "num_b": 0.7, "num_c": 4, "cat_a": "red", "cat_b": "small"}]}'
```

For regression, upload `synthetic_regression.csv` and train with `"target_column": "value"`.

**Offline (no API, no database):**
```bash
python scripts/profile_dataset.py datasets/examples/synthetic_classification.csv --target label
python scripts/train_model.py datasets/examples/synthetic_classification.csv --target label
```
`profile_dataset.py` writes `reports/profile/summary.json` and PNG charts (missing values,
distributions, correlation heatmap).

### Training request options

| Field | Default | Meaning |
|---|---|---|
| `dataset_id` | required | ID returned by the upload. File paths are never accepted. |
| `target_column` | required | Column to predict |
| `problem_type` | inferred | `classification` or `regression`. Inference: text/bool → classification; integers with ≤ 20 distinct values → classification; otherwise regression. Set it explicitly when that guess is wrong. |
| `algorithm` | `linear` | `linear` (LogisticRegression / Ridge) or `random_forest` |
| `feature_columns` / `exclude_columns` | all others / none | Exclude IDs and anything derived from the target |
| `test_size` / `validation_size` | `0.2` / `0.2` | Fractions of the cleaned dataset |
| `random_state` | `42` | Reproducible splits and forests |
| `drop_duplicates` | `true` | Drop exact duplicate rows before splitting |

### What the pipeline does

1. Drops rows with a missing target and selects features. The target, excluded, all-missing,
   constant, datetime and free-text/ID-like columns are left out, and each is reported in
   `training_metadata.dropped_columns`.
2. Removes exact duplicate rows **before** splitting, so copies can't sit in both train and test.
3. Splits into train/validation/test, stratified for classification when every class is large enough.
4. Fits a single sklearn `Pipeline`: a `ColumnTransformer` (numeric: median impute + scale;
   categorical: constant `__missing__` impute + one-hot, capped at 50 categories, unknown
   categories tolerated), then the estimator. Fitting uses the **training split only**.
5. Reports metrics on train, validation and test, plus a `Dummy*` baseline on test:
   - Classification: accuracy, balanced accuracy, macro precision/recall/F1, confusion matrix,
     log loss, ROC AUC (binary) or one-vs-rest macro AUC (multiclass).
   - Regression: MAE, RMSE, median absolute error, R².
6. Saves the pipeline plus metadata with joblib under `MODEL_DIR` using a generated name, and
   records its SHA-256 in the database.

### Prediction input rules

- Each record must contain **exactly** the model's features (`feature_schema` from
  `GET /models/{id}`). Unknown or missing keys give 422, with per-record, per-field details.
- Numeric features must be finite JSON numbers (strings and booleans are rejected).
  Categorical features accept strings, numbers or booleans.
- `null` and empty strings are rejected unless `"allow_missing": true`. In that case they are
  imputed the same way as in training.
- At most `MAX_PREDICTION_RECORDS` records per request.

### File handling and security

- Only `.csv` (UTF-8) and `.xlsx` are accepted, and the content is checked as well as the
  extension: CSVs must not contain binary bytes, and `.xlsx` files must be real zip workbooks.
  Workbooks with an extreme compression ratio (zip bombs) are rejected.
- Size is enforced while streaming, and partial files are deleted on any failure. Row and
  column limits apply after parsing, and duplicate header names are rejected.
- Files are stored under server-generated names. The client filename is kept only as display
  metadata. All storage paths are resolved through `resolve_within`, which rejects `..`,
  separators, absolute paths and symlink escapes.
- joblib/pickle can execute code when loaded. Artifacts are only loaded from `MODEL_DIR`, by
  generated name, after their SHA-256 matches the recorded hash. Never place untrusted
  `.joblib` files there.

## AI services (Part 3)

Every AI feature is optional. The core API starts and serves without any AI package and without
an API key (the test suite checks this). A feature whose dependency is missing returns
**503 `optional_dependency_missing`** with the exact install command. Chat without a key returns
**503 `provider_not_configured`**. `GET /api/v1/ai/status` shows which packages are installed,
whether the provider is configured (the key itself is never shown), and which models are loaded.

### Install what you need

| You want | Install | Download / disk |
|---|---|---|
| LLM chat, token counting, text analysis | `pip install -r requirements-llm.txt` | ~15 MB of packages, plus ~3.6 MB of tiktoken encodings on first use |
| Local embeddings + classification | PyTorch (below), then `pip install -r requirements-nlp.txt` | PyTorch CPU ~200 MB (CUDA builds 2+ GB), models ~360 MB |

**PyTorch.** Pick the build that matches your hardware; it isn't installed for you:

```bash
# CPU only (Windows/Linux):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# NVIDIA GPU: get the command for your CUDA version at https://pytorch.org/get-started/locally/
# Apple Silicon (MPS included): pip install torch torchvision
```

**Models are never downloaded at startup.** They load lazily on the first request, which can
take a while if the model has to be downloaded. To pre-download them:

```bash
python scripts/download_models.py     # embedding model (~90 MB) + classifier (~270 MB)
```

Models are cached in `AI_MODEL_CACHE_DIR`, or `~/.cache/huggingface` if unset. After
downloading, set `AI_ALLOW_MODEL_DOWNLOADS=false` to run offline; this sets `HF_HUB_OFFLINE`.
`trust_remote_code` is always off.

### Endpoints

| Method & path | Purpose | Needs |
|---|---|---|
| `GET /api/v1/ai/status` | Installed extras, provider config, loaded models | — |
| `POST /api/v1/tokens/count` | Tokens for `text` or chat `messages` (tiktoken; falls back to a flagged chars÷4 estimate) | `llm` (optional) |
| `POST /api/v1/embeddings` | `{"texts": [...], "normalize": true}` → vectors with an explicit `dimension` | torch + `nlp` |
| `POST /api/v1/nlp/classify` | Sentiment (POSITIVE/NEGATIVE) with `top_k` scores | torch + `nlp` |
| `POST /api/v1/llm/chat` | Chat completion (OpenAI Responses API) | `llm` + `OPENAI_API_KEY` |
| `POST /api/v1/nlp/analyze` | Summarise text of any length (map-reduce) and score sentiment | `llm` + `agents` + key (+ `nlp` for sentiment) |

Examples:

```bash
curl -s -X POST localhost:8000/api/v1/tokens/count -H "Content-Type: application/json" \
  -d '{"text": "Tokenization splits text into subword units."}'
curl -s -X POST localhost:8000/api/v1/embeddings -H "Content-Type: application/json" \
  -d '{"texts": ["first sentence", "second sentence"]}'
curl -s -X POST localhost:8000/api/v1/llm/chat -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "What is an embedding?"}], "max_output_tokens": 300}'
```

**Local NLP demo** (no API key needed): `python scripts/nlp_demo.py` prints cosine similarities
between sentences and their sentiment. `python scripts/evaluate_classifier.py` scores the
classifier on SST-2 using Hugging Face `datasets` + `evaluate`.

### Design

- **Interfaces and dependency injection.** `ChatService`, `EmbeddingBackend` and the pipeline
  loader are small Protocols/callables. `AIServices` (on `app.state.ai`) builds services lazily,
  and routes receive them through FastAPI dependencies, which tests override with fakes.
- **Model caching.** `ModelCache` is a thread-safe LRU (`AI_MAX_LOADED_MODELS`). Concurrent
  first requests load a model **once**. Failed loads aren't cached and return
  503 `model_load_failed`.
- **Devices.** `AI_DEVICE=auto` picks CUDA, then Apple MPS, then CPU. Asking for `cuda`/`mps`
  when it isn't available gives a clear error rather than a silent fallback.
- **Timeouts and concurrency.** Local inference runs in a bounded pool
  (`AI_MAX_CONCURRENT_INFERENCES`) with `AI_INFERENCE_TIMEOUT_SECONDS`. Running past it returns
  504 `inference_timeout`; the abandoned computation finishes in the background, because Python
  threads can't be killed. Provider calls use `OPENAI_TIMEOUT_SECONDS`, and the SDK retries
  connection errors, 429 and 5xx up to `OPENAI_MAX_RETRIES` times with backoff.
- **Embeddings.** Requests are processed in `EMBEDDING_BATCH_SIZE` batches, each output's shape
  is checked against the model's dimension, and non-finite values are rejected. Set
  `EMBEDDING_DIMENSION` to pin the vector size you store; a model with a different size is
  rejected instead of silently corrupting a vector store.
- **Framework use is deliberately narrow.** LangGraph runs one workflow (`/nlp/analyze`:
  measure → split → summarise each chunk → combine → classify, with conditional routing).
  LangChain provides only token-aware text splitting. Both call this project's own OpenAI
  service, so there's no second LLM client. **LlamaIndex** has a dependency group but no code
  yet: without RAG it has no use case here, and it's planned for Part 4.

### LLM limits, errors and privacy

- **Limits.** Requests are validated before any provider call: message count, total characters,
  input tokens (`LLM_MAX_INPUT_TOKENS`), output budget (`LLM_MAX_OUTPUT_TOKENS`), and the model
  allow-list (`OPENAI_MODEL` + `OPENAI_ALLOWED_MODELS`), which keeps cost under control.
- **Default model.** `gpt-5.4-mini` is configurable. GPT-5-family reasoning models may reject
  `temperature`; leave it unset for them. Reasoning also consumes output tokens, so if
  `finish_reason` is `max_output_tokens`, raise `max_output_tokens`.
- **Error mapping.** Provider errors map to stable codes:

  | Provider failure | HTTP | `error.code` |
  |---|---|---|
  | No key configured | 503 | `provider_not_configured` |
  | 401/403 bad key | 502 | `provider_authentication_failed` |
  | 429 rate limit | 429 + `Retry-After` | `provider_rate_limited` |
  | 429 quota | 429 | `provider_quota_exceeded` |
  | Timeout | 504 | `provider_timeout` |
  | Network / 5xx | 502 | `provider_unavailable` |
  | Unknown model | 502 | `provider_model_not_found` |
  | 400/422 e.g. context too long | 422 | `provider_rejected_request` (`details.provider_code`) |

- **Privacy.** The API key is never logged or returned. Prompts and completions aren't logged
  unless `LLM_LOG_CONTENT=true`; the SDK's own DEBUG request logging is muted as well. Requests
  are sent with `store=false`. Provider error text isn't passed on to clients.

## Running tests and lint

```bash
pytest                          # all tests (PostgreSQL ones skip without TEST_DATABASE_URL)
pytest tests/unit               # unit tests only
pytest --cov=app                # with coverage
ruff check . ; ruff format --check .
```

AI tests never download models or call paid APIs. Local models are replaced by deterministic
fakes. OpenAI tests run the **real SDK** against an in-memory `httpx.MockTransport`, so actual
SDK exceptions (timeouts, 401, 429 with `Retry-After`, quota, 5xx, network errors) are raised
and mapped. `tests/integration/test_optional_dependencies.py` starts the app in a subprocess
where every optional AI package is blocked and checks that it still serves. Tests needing
`openai`/`langgraph` skip themselves if those aren't installed.

Unit tests use an **in-memory SQLite database as a test double** for PostgreSQL (see
[tests/conftest.py](tests/conftest.py)). The application itself never falls back to SQLite.

PostgreSQL integration tests (`@pytest.mark.integration`, in `tests/integration/test_database.py`)
need a **disposable** database. They run inside a transaction that is rolled back:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://aiproject:<password>@localhost:5432/aiproject_test"; pytest -m integration
```
```bash
TEST_DATABASE_URL=postgresql+psycopg://aiproject:<password>@localhost:5432/aiproject_test pytest -m integration
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: No module named 'app'` | Run from the project root with the venv active |
| `uvicorn: command not found` | Activate the venv, or `python -m uvicorn app.main:app --reload` |
| `ConfigurationError: Invalid configuration -> ...` | Fix the listed variables in `.env` / environment |
| Dataset/model endpoints return 503 `database_not_configured` | Set `DATABASE_URL` and restart |
| `/api/v1/health` returns 503 | Run `python scripts/check_db.py` for the failure category and hint |
| `relation "datasets" does not exist` | `alembic upgrade head` |
| `No module named 'psycopg2'` | Use `postgresql+psycopg://` (plain `postgresql://` is rewritten automatically) |
| 415 on upload | Only `.csv` and `.xlsx`; convert legacy `.xls` to `.xlsx` |
| 400 "CSV files must be UTF-8" | Re-save as "CSV UTF-8" (Excel) or convert the encoding |
| 422 `training_error` | Read `error.details` / `message` — e.g. too few rows, single-class target, wrong `problem_type` |
| `InconsistentVersionWarning` when predicting | Model trained with another scikit-learn version; retrain |
| 503 `optional_dependency_missing` | Run the install command in `error.details.install` (PyTorch first for local models) |
| 503 `provider_not_configured` | Set `OPENAI_API_KEY` in `.env` and restart |
| 502 `provider_authentication_failed` | Key is invalid/revoked or lacks access to the model |
| 429 `provider_quota_exceeded` | Add billing/credits for the OpenAI account |
| 503 `model_load_failed` | Wrong model name, no network (or `AI_ALLOW_MODEL_DOWNLOADS=false` before downloading), or not enough disk/RAM; see the server log |
| `AI_DEVICE=cuda but CUDA is not available` | Install a CUDA build of PyTorch, or set `AI_DEVICE=cpu` |
| First embedding/classify request is very slow | It's downloading and loading the model; pre-download with `scripts/download_models.py` |
| `tokens/count` returns `"approximate": true` | tiktoken isn't installed, or couldn't download its encoding (offline). Set `TIKTOKEN_CACHE_DIR` to a pre-filled cache |
| Port 8000 in use | `uvicorn app.main:app --reload --port 8001` |
| Path contains spaces (Windows) | Quote it: `cd "C:\path with spaces\AIProject"` |

## Known limitations

- Training and AI inference run synchronously in the request threadpool. Large jobs tie up a
  worker, and a timed-out local inference keeps computing in the background.
- LLM calls aren't streamed, and there's no per-user rate limiting or spend tracking yet.
- The local NLP path (PyTorch, transformers, sentence-transformers) is exercised with fakes in
  CI. It hasn't been run end-to-end in this repository's verified environment.
- No authentication or authorization yet. Do not expose the API publicly.
- Datasets and models cannot be deleted through the API yet. Artifacts live on local disk.
- One-hot encoding caps each categorical column at 50 categories. Datetime and free-text
  columns are excluded rather than engineered.
- No hyperparameter search. The validation split is reported but not yet used for model selection.

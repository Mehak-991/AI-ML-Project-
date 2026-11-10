# Registration API Diagnostic

Investigated 2026-11-11. **Read-only:** safe GET requests, file reads, `docker exec` greps and process
listings only. Nothing was restarted, rebuilt, deployed, written to the database or configuration, and
no user was created.

## Root cause

**The page showing "The API server is not running" is not the Docker stack's frontend. It is the Vite
development server (`npm run dev`) running on this machine, which has no API to talk to.**

- A Vite dev server for this project's `frontend` folder is running (`node ...\frontend\node_modules\vite\bin\vite.js`,
  started by `npm run dev`, pid 30596). It answers on `http://localhost:3000/` (IPv6 `::1`).
- `frontend/vite.config.ts` makes that server proxy every `/api` request to **`http://127.0.0.1:8000`**.
- **Nothing listens on port 8000 on the host.** The Docker `app` container only exposes 8000 on the
  internal Docker network (`docker port aiproject-app-1` prints nothing), by design.
- So every API call made through the dev server fails: the proxy cannot connect and answers
  **HTTP 502 with an empty body**.
- In `frontend/src/services/api.ts` (`parseApiError`, lines 193 to 202) a 502 is turned into
  "The API server is not running. Start it with: python -m uvicorn ..." **only when
  `import.meta.env.DEV` is true**. A development build is the only place that text can appear.

The stack itself is fine: the same endpoints answer correctly through nginx on port 80 (see Evidence).
The "all four containers healthy" and "health returns 200" observations are both true and unrelated to
what the dev page does, because the dev page never talks to nginx or Docker.

**What I could not observe:** the browser's address bar and network tab. The conclusion is inferred
from the evidence below; please confirm it with the one-step check in "How to confirm".

## Exact failing endpoint

The registration request is `POST /api/v1/auth/register` (frontend call `authApi.register`, then
`login`). Through the dev server this is `POST http://localhost:3000/api/v1/auth/register`, which the
dev proxy forwards to `http://127.0.0.1:8000/api/v1/auth/register` and fails with **502**. I did not
send a POST (it would create a user). The equivalent GETs show the same failure on the same prefix:

| Request | Result |
|---|---|
| `GET http://localhost:3000/api/v1/health` | **502**, empty body |
| `GET http://localhost:3000/api/v1/auth/me` | **502**, empty body |
| `GET http://localhost:3000/api/v1/auth/register` | **502**, empty body |
| `GET http://127.0.0.1:8000/health` (the proxy target) | connection refused (`000`) |

## Relevant files

| File | Role |
|---|---|
| `frontend/vite.config.ts` | Dev-server proxy: `/api`, `/docs`, `/openapi.json` to `http://127.0.0.1:8000` (hard-coded) |
| `frontend/src/services/api.ts` | `baseURL: import.meta.env.VITE_API_BASE_URL \|\| '/api/v1'` (line 12); `parseApiError` 502 branch with the DEV-only message (lines 193 to 202); `getHealth()` calls `/health` relative to the base URL = `/api/v1/health` (line 372) |
| `frontend/src/context/AuthContext.tsx` | `register()` catches the error, stores `parseApiError(err).message` (lines 62 to 70) |
| `frontend/src/components/AuthModal.tsx` | The registration form and the stale text (lines 152 to 155) |
| `frontend/nginx.conf` (live image: `/etc/nginx/conf.d/default.conf`) | Production `/api/` proxy to `app:8000` |

## Evidence

1. **Base URL is not misconfigured.** There are no `frontend/.env*` files. The live p21 bundle contains
   `baseURL:` followed by the literal `` `/api/v1` ``, no `VITE_API_BASE_URL`, no `localhost:8000`, no
   `127.0.0.1:8000`. In production the browser calls the same origin and nginx routes it.
2. **The message cannot come from any built frontend.** The text "API server is not running" appears in
   **0** bundles of the live container and of the `pre-p21`, `0.5.0-p20test`, `0.5.0-p21` and
   `0.5.0-p22` frontend images. (The production build removes that branch; the surrounding
   "temporarily unavailable" text is present in p21 and p22.) The dev server serves unminified source,
   where the branch is active.
3. **Nginx and the API path work.** Through the stack on port 80:
   `GET /api/v1/health` = 200 (`{"status":"ok","version":"0.4.0","environment":"production",...}`),
   `GET /api/v1/auth/me` = 401 with the JSON error envelope (the correct unauthenticated answer),
   `GET /api/v1/auth/register` = 405 `method_not_allowed` (the route exists; only POST is allowed).
   The live nginx config proxies `/api/` to `$api_upstream` (`app:8000`) with Docker DNS
   (`resolver 127.0.0.11`).
4. **Which endpoint the frontend calls.** Only `DeploymentMonitoringPage` calls `getHealth()`
   (`/api/v1/health`); the registration page makes no health call. The 'API not running' state comes
   from the failed `POST /auth/register`, not from a health probe. The version `0.4.0` you saw is the
   p21 backend's package version (p22 reports `0.5.0` plus a `release` field).
5. **No CORS, timeout or parsing problem.** Browser and API are the same origin in both setups (the
   dev server proxies `/api`), so CORS is not involved. The failure is immediate (connection refused),
   not a timeout (nginx allows 300 s). The 502 has an empty body, so `parseApiError` falls through to its
   status branch; there is nothing to mis-parse.
6. **A trap worth knowing:** `GET http://localhost/health` returns **200 with the SPA's `index.html`**
   (nginx serves the single-page app for unknown paths). Only `/api/v1/health` is the API's health
   check. Any tool that probes `/health` on port 80 will report a healthy API even when the API is down.
7. **p21 versus p22 frontend (item 6).** `frontend/src`, `index.html`, `package*.json` and
   `vite.config.ts` are **unchanged** between the p21 build commit (`c92bbf8`) and `HEAD`, and the p21 and
   p22 images contain the **identical** set of content-hashed JS/CSS files. So the p22 frontend has
   the same behaviour, including the stale text below. Only the nginx files differ (p22 adds
   `server-common.inc` and `00-proxy-trust.conf`).
8. **Why the old first-user message is still shown.** It is hard-coded in `AuthModal.tsx:152-155`:
   "New accounts have Viewer (read-only) access. An administrator can grant more. The very first
   account on a new installation becomes the Administrator." Phase 22 changed the backend (public
   registration never creates an admin) and the docs but **did not touch the frontend**, so this text
   is stale in the dev server, in p21, **and in the committed p22 frontend** (image `ca71d9937a67`).
   It would mislead users after the p22 deployment.

## How to confirm (30 seconds, no changes)

1. Look at the browser address bar of the page that shows the message. Expected: `localhost:3000`.
2. Open DevTools, Network tab, press Register. Expected: `POST /api/v1/auth/register` with status
   502 and an empty response.
3. Open `http://localhost/` (port 80, no port number) instead. Expected: registration reaches the API
   and no "not running" message.

## Recommended minimal fix

Nothing in the Docker stack, nginx or the API needs to change for the connectivity symptom.

1. **Connectivity (no code change):** use the stack at `http://localhost/`, or stop the dev server
   (`npm run dev`, pid 26668/30596). If you want to keep using the dev server against this stack, make
   its proxy target configurable (below).
2. **`frontend/vite.config.ts` (small code change):** read the proxy target from an environment variable,
   default unchanged:
   `const target = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000'`, used for the three proxy
   entries. Then `VITE_DEV_API_TARGET=http://localhost npm run dev` (PowerShell:
   `$env:VITE_DEV_API_TARGET="http://localhost"; npm run dev`) proxies the dev page through nginx to the
   running stack, with no port published and no Docker change.
3. **`frontend/src/components/AuthModal.tsx` (text fix, needed for p22):** replace the registration
   hint with text that matches the backend, for example: "New accounts have Viewer (read-only) access.
   An administrator can grant more." and drop the "first account becomes the Administrator" sentence.
   This needs a **frontend rebuild**, so it changes the frontend image: either rebuild
   `aiproject-frontend:0.5.0-p22` before it is ever deployed (it has not been deployed), or ship the fix
   as the next tag. I recommend fixing it before the p22 deployment.
4. **Optional, small:** make the DEV-only 502 message name the proxy target, so a mismatch like this is
   self-explanatory (for example "The dev proxy could not reach http://127.0.0.1:8000").

No change to nginx, Compose, `.env`, the database or the backend is needed. Nothing here is deployed
or applied; I am waiting for your approval before touching any of it.

## Regression tests

The frontend has no test runner (scripts are only `dev`, `build`, `lint`; CI runs `npm ci` and
`npm run build`), so the cheapest protection fits the existing Python test suite and CI.

1. `tests/unit/test_frontend_consistency.py` (static, runs in CI today):
   - fail if any file under `frontend/src` contains the phrase "first account" together with
     "Administrator" (stale bootstrap claim);
   - fail if `vite.config.ts` hard-codes the proxy target without the `VITE_DEV_API_TARGET` override;
   - assert `frontend/src/services/api.ts` keeps `baseURL` defaulting to `/api/v1` (relative, same
     origin) and has no absolute `http://` API URL.
2. `scripts/check_stack.py` (smoke test run against a deployed or local stack, also usable in the
   deployment checklist): `GET <origin>/api/v1/health` must be JSON with `status == "ok"` (not HTML);
   `GET <origin>/api/v1/auth/me` must be 401 JSON; `GET <origin>/api/v1/auth/register` must be 405; and
   it warns if `GET <origin>/health` returns HTML, so the SPA-fallback trap is visible.
3. Optional follow-up if the team wants UI tests: add Vitest and React Testing Library, then test that
   `parseApiError` returns the production text for a 502 when `import.meta.env.DEV` is false, and that
   the register form shows no "first account becomes Administrator" text. This adds dependencies, so it
   needs your decision.

Run before and after any fix: `python scripts/check_stack.py --origin http://localhost`.

## Status of the system during this investigation

Unchanged: the four `aiproject` containers are the same p21 containers (healthy), the git working tree
is clean, no `.env` edits, no database writes (no POST requests were made), no Docker volume was
touched.

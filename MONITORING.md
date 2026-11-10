# Monitoring (Prometheus)

`GET /metrics` is served by the API on `app:8000`. Nginx answers **404** for `/metrics` on the public
entry point on purpose, so metrics are never reachable from the internet. `compose.monitoring.yaml`
adds an opt-in Prometheus that scrapes the API over the internal Docker network with a bearer token.
Nothing in this file is part of the default stack.

## Security model

- The API checks `Authorization: Bearer <METRICS_TOKEN>` with a constant-time comparison when
  `METRICS_TOKEN` is set. **When it is not set, `/metrics` is open to any container on the internal
  network.** Set it before enabling monitoring. `scripts/preflight.py` warns while it is unset.
- Prometheus reads the token from a file (`monitoring/secrets/metrics_token`, ignored by Git), never
  from the config file, so the token does not appear in `prometheus.yml`, compose output or logs.
- Prometheus is published on `127.0.0.1:9090` only. It has no authentication of its own: do not
  change `PROMETHEUS_BIND` to a public address without putting authentication in front.
- The container runs with a read-only root filesystem, no capabilities, `no-new-privileges` and a
  512 MB memory limit. Its data lives in a new volume (`prometheus_data`); existing volumes are not
  involved.

## Set up (PowerShell, from the project folder)

```powershell
# 1. Create the token once. It is written to a file and to .env.production, not printed.
$token = python -c "import secrets; print(secrets.token_urlsafe(32), end='')"
[IO.File]::WriteAllText("$PWD\monitoring\secrets\metrics_token", $token)
Add-Content .env.production "METRICS_TOKEN=$token"
Remove-Variable token

# 2. Recreate the API so it starts enforcing the token (short interruption of app only).
$env:APP_VERSION = "0.5.0-p21"
docker compose --env-file .env.production up -d --no-build --no-deps app

# 3. Start Prometheus.
docker compose --env-file .env.production -f compose.yaml -f compose.monitoring.yaml up -d --no-build prometheus
```

On Linux, the token file must be readable by the Prometheus user (`nobody`, uid 65534): for example
`chmod 644 monitoring/secrets/metrics_token` on a single-user host, or add `user: "<uid>"` to the
service. Keep the folder out of backups that leave the machine.

## Verify

```powershell
# Prometheus sees the target as up (requires the token to be right):
curl.exe -s http://127.0.0.1:9090/api/v1/targets

# The API refuses an unauthenticated scrape from inside the network (expect HTTP 401):
docker compose --env-file .env.production exec app python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/metrics')"

# The public entry point still hides it (expect 404):
curl.exe -s -o NUL -w "%{http_code}" http://localhost/metrics
```

Useful queries: `aiml_worker_health_status == 0` (worker down), `aiml_jobs_by_status{status="failed"}`,
`aiml_jobs_by_status{status="queued"}` growing, `increase(aiml_predictions_total{status="error"}[15m])`.

## Rotating the token

Write a new value to `monitoring/secrets/metrics_token` and to `METRICS_TOKEN`, recreate `app`
(`up -d --no-deps app`), then `docker compose ... restart prometheus`. Until both match, the target
shows `down` with HTTP 401, which is the correct failure mode.

## Unchanged by this setup

The worker heartbeat file and `scripts/check_worker_health.py` container health check are untouched;
`aiml_worker_health_status` reads the same heartbeat.

## What was tested

The scrape configuration was run with the real `prom/prometheus:v3.5.0` image against a stub target
that returns 401 unless the exact bearer token arrives: with the right token file the target was `up`
and the metric was ingested; with a wrong token the target was `down` (HTTP 401). `promtool check
config` passes. Not tested here: scraping the real API with `METRICS_TOKEN` set (the token check
itself is covered by the existing metrics unit tests), long-running retention, Grafana.

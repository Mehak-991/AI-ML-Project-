# TLS / HTTPS Deployment

HTTPS is **opt-in**. The default stack (`compose.yaml`) still serves plain HTTP on `FRONTEND_PORT`,
so local development is unchanged. No certificate ships with the project, and none is generated for
you: you provide one.

Choose a setup:

| | A. Nginx terminates TLS | B. A proxy / load balancer terminates TLS |
|---|---|---|
| Use when | One host, you have a certificate | Caddy, Traefik, a cloud load balancer, or another proxy already handles TLS |
| Files | `compose.tls.yaml`, `frontend/nginx.tls.conf` | `frontend/proxy-trust.conf` (mounted) |
| API told "HTTPS" via | Nginx's own scheme | `X-Forwarded-Proto` from the proxy you list as trusted |

## What the configuration guarantees

- **`X-Forwarded-Proto` is only believed from a trusted proxy.** `frontend/proxy-trust.conf` defines
  `$forwarded_proto`. It equals nginx's own scheme unless the request comes from an address listed in
  the `geo` block. A client that sends `X-Forwarded-Proto: https` itself is ignored (tested).
  **Nothing is trusted by default.**
- **HSTS** (`Strict-Transport-Security: max-age=31536000`) is sent only when the original request was
  HTTPS, never over plain HTTP. It starts without `includeSubDomains` and `preload`; add those only
  when every subdomain is served over HTTPS, because browsers will refuse HTTP for the whole
  period. While testing, lower `max-age` in `frontend/proxy-trust.conf` (for example `300`).
- Mode A: TLS 1.2 and 1.3 only, modern AEAD ciphers, no session tickets, `server_tokens off`.
  Port 80 redirects everything to HTTPS (301) except `/healthz`, which keeps the container health
  check working.
- `/metrics` stays hidden (404) in both modes. CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`
  and `Permissions-Policy` are unchanged and present on every route.
- **Cookies:** the application sets none. Access and refresh tokens are sent in `Authorization`
  headers and kept in the browser's `sessionStorage`, so `Secure` / `HttpOnly` / `SameSite` flags do
  not apply. CORS defaults to same-origin in production.

## A. Nginx terminates TLS

1. Put `fullchain.pem` (certificate plus intermediates) and `privkey.pem` in one folder outside the
   repository. Keep the key readable only by you and Docker.
   *Local testing only:* a tool such as `mkcert` can create a trusted local certificate. Never use a
   self-signed certificate for real users.
2. Start with the override (PowerShell):

```powershell
$env:APP_VERSION  = "0.5.0-p21"             # your release tag
$env:TLS_CERT_DIR = "C:\path\to\certs"      # holds fullchain.pem and privkey.pem
python scripts\preflight.py --env-file .env.production --check-docker
docker compose --env-file .env.production -f compose.yaml -f compose.tls.yaml up -d --no-build --wait frontend
```

   Only `frontend` is recreated; the database, volumes, `app` and `worker` are untouched.
3. Use port **443** (the default `FRONTEND_TLS_PORT`). The HTTP-to-HTTPS redirect drops the port
   number, so a non-standard HTTPS port would send browsers to the wrong place.
4. Set `server_name` in `frontend/nginx.tls.conf` to your domain if you want unknown `Host` headers
   rejected; the default `_` accepts any.

Verify:

```powershell
curl.exe -sI http://your-domain/                  # expect 301 and a Location: https://... header
curl.exe -sI https://your-domain/                 # expect 200 and Strict-Transport-Security
curl.exe -s  https://your-domain/api/v1/health    # "release" shows the live tag
docker compose --env-file .env.production logs frontend --tail 20
```

## B. A proxy / load balancer terminates TLS

1. The proxy forwards HTTP to nginx and sets `X-Forwarded-Proto: https` and `X-Forwarded-For`.
2. Copy `frontend/proxy-trust.conf`, list **only** the proxy's address or subnet in the `geo` block
   (`10.0.0.5/32 1;`), and add, in the same file, the lines that make nginx use the real client IP:

```nginx
set_real_ip_from 10.0.0.5/32;       # the proxy, exactly as in the geo block
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

3. Mount it over `/etc/nginx/conf.d/00-proxy-trust.conf` (read-only) in a compose override, then
   recreate `frontend` only. Keep `FORWARDED_ALLOW_IPS` for the API pointing at nginx's fixed address
   (`FRONTEND_PROXY_IP`, default `172.21.0.10`). **Do not** put the proxy there.
4. Publish nginx only to the proxy (for example `"127.0.0.1:${FRONTEND_PORT:-80}:80"`) so nothing
   bypasses TLS.

Requirements for the proxy: it must **overwrite**, not append to, any `X-Forwarded-Proto` supplied
by clients, and it must be the only route to nginx. Check that `client_ip` in
`docker compose logs app` shows real client addresses; otherwise all users share one rate-limit
budget.

## What was tested

Run on throwaway containers (read-only root, dropped capabilities) with a temporary self-signed
certificate that was deleted afterwards: both nginx configs pass `nginx -t`; plain HTTP stays plain;
TLS mode redirects (301), serves HSTS, reports `https` to the upstream, refuses TLS below 1.2 and
accepts 1.3; a spoofed `X-Forwarded-Proto` is ignored from untrusted sources and honoured from a
trusted subnet; `/metrics` returns 404 in every mode. **Not tested:** a certificate from a real CA,
browsers, or a specific load balancer product.

## Rollback

Start without the override (`docker compose -f compose.yaml up -d --no-build frontend`). Browsers that
already received HSTS keep demanding HTTPS until `max-age` expires, so lower it before the first
production rollout.

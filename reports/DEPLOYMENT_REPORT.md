# Deployment Report

**Status: nothing has been deployed in this phase.** Production still runs release `0.5.0-p21` on
database revision `0013`. This report records what was verified on disposable environments, and the
exact procedure and approval gates for the production rollout.

## 1. What was verified (disposable stack only)

A separate Compose project (`aiproject-rc2`, port 18099, its own network subnet, database on tmpfs,
data on bind-mounted scratch folders, **no Docker volumes created**) was built from the committed
tree with `git archive` and run, then torn down with `docker compose down` (no `-v`).

| Check | Result |
|---|---|
| Backend and frontend images build | ✅ `aiproject-backend:0.6.0-rc2` (`27c6e4705422`), `aiproject-frontend:0.6.0-rc2` (`4aa168228812`) |
| Services start and become healthy | ✅ db, app, worker, frontend healthy; migration service ran `alembic upgrade head` (14 revisions) |
| `http://127.0.0.1:18099/` | ✅ 200 (React app) |
| `/api/v1/health` | ✅ `status: ok`, database `ok`, release `0.6.0-rc2` |
| `/metrics` at the public edge | ✅ 404 (internal only) |
| `/docs`, `/openapi.json` | ✅ 404 with default settings |
| Security headers, CORS, error shapes | ✅ see `SECURITY_AUDIT.md` |
| Full end-to-end run (97 checks) | ✅ all passed |
| Persistence | ✅ after `docker compose restart app worker frontend`: identical user, dataset, model, audit and prediction counts and the same 8 model files and 2 upload files on disk |
| `scripts/check_stack.py` | ✅ passed |

The `http://localhost/` and `http://localhost/api/v1/health` addresses named in the brief are the
same routes on the default port (`FRONTEND_PORT=80`); they were verified on port 18099 because port 80
belongs to the running production stack.

**Important:** the `0.6.0-rc2` images were built from commit `321babd`. Later commits changed only
documentation, `scripts/e2e_check.py`, CI and two unused-variable edits in frontend files. The release
images **must be rebuilt from the final merged commit** and re-verified with the same procedure
before production use. Do not deploy `rc2` as is.

## 2. What cannot be claimed

* **Public deployment and HTTPS are not done.** They need a domain, DNS and a certificate.
  `compose.tls.yaml` and `TLS_DEPLOYMENT.md` contain the configuration.
* **GitHub Actions** results for the latest commits could not be read from this environment (the
  unauthenticated API was rate-limited). Every CI step was reproduced locally.

## 3. Unexplained event on production (read-only observation)

While checking production health I noticed that the production `app` and `worker` containers
(`aiproject-app-1`, `aiproject-worker-1`) were last **started at 2026-11-11 11:36:42Z** after a clean
`SIGTERM` shutdown at 11:36:32Z, whereas `db` and `frontend` started the previous day. The containers
are the same ones (created 2026-11-10 19:24Z), still on the p21 image `83b37eaeee4a`, restart count 0,
healthy, and the database is still at revision `0013`. **I did not run any command against the
`aiproject` project**, and I cannot identify who or what restarted them (Docker keeps no event
history for that window). Please check whether you or a tool restarted them.

## 4. Production rollout plan (requires explicit approval for each gate)

### Approval gates (nothing below may start without your written approval)

Each gate lists the action, the impact and the way back.

| # | Action | Impact / downtime | Rollback |
|---|---|---|---|
| G1 | Merge this branch into `main` by pull request (merge commit) | None on production | Revert merge commit via a new commit |
| G2 | Build final release images from the merged commit and verify them again on a disposable stack | None on production | Delete the new tags |
| G3 | Take a fresh, checksummed production backup and prove it restores into a separate database | Read-only on production, seconds | — |
| G4 | Stop `frontend`, `app`, `worker` (database stays up) | **Downtime starts**; estimate 5–15 minutes in total for G4–G8 on the current small database | Start the old containers (`0.5.0-p21` images are kept) |
| G5 | Run migration `0014` (one-off container, `alembic upgrade 0014`) | Part of downtime; it aborts and changes nothing if an `ml_engineer` account exists without an explicit mapping | Restore the G3 backup into a separate database |
| G6 | Create the production superadmin with `scripts/create_superadmin.py` for the account **you name** (new account, or `--promote` of one existing account) | Part of downtime | Restore the G3 backup |
| G7 | Update production `.env` (`APP_VERSION`, leave `PASSWORD_REHASH_ON_LOGIN=false`) and start the new images | Downtime ends when healthy | Revert `.env`, start the p21 images against the restored copy |
| G8 | Verify (health, E2E-lite as superadmin, audit log) | | |
| G9 | Change DNS / enable HTTPS (separate, later) | Depends on host | Revert DNS |

### Prerequisites you must complete first

1. **Rotate the live admin password** and confirm it (see `SECURITY_AUDIT.md` S-01). I will not ask
   for the password.
2. Name the account that becomes superadmin and whether it is new or the existing admin.
3. Choose the rollback method (backup restore is the default; a production downgrade is **not**
   recommended because it is lossy: `superadmin` and `admin` become indistinguishable).

### Exact commands (PowerShell, from the project directory; do not run until approved)

```powershell
# G3 backup (existing script writes a .sha256 next to the dump) and restore proof
python scripts/backup_db.py --output-dir backups/pre-rbac-v2-final
python scripts/restore_db.py --backup <file>.sql.gz --target-db aiproject_restore_check --confirm

# G4 stop traffic (keep db)
docker compose --env-file .env.production stop frontend app worker

# G5 migrate with the NEW image, app stopped
docker compose --env-file .env.production run --rm --no-deps app alembic upgrade 0014

# G6 create / promote the named superadmin (hidden prompt; add --promote for an existing account)
docker compose --env-file .env.production run --rm --no-deps -it app python scripts/create_superadmin.py --email <the account you choose>

# G7 start the new release
docker compose --env-file .env.production up -d --no-deps app worker frontend

# G8 verify
python scripts/check_stack.py --origin http://localhost
```

### Rollback (default: restore, never downgrade)

1. `docker compose --env-file .env.production stop frontend app worker`.
2. Restore the verified G3 backup into a **new** database name; point `DATABASE_URL`/`POSTGRES_DB` at it.
3. Set `APP_VERSION` back to `0.5.0-p21`, start the p21 images. All writes after the backup are lost;
   the migrated database is kept untouched for analysis.
4. Never run `docker compose down -v`, never delete volumes.

### Why p21 cannot simply be started against a migrated database

Verified in the p21 image: roles `user` and `superadmin` fail response validation (HTTP 500 on
`/auth/me` and on the whole user list), and `user`/`superadmin` accounts get 403 on every role-gated
route. p21 also cannot verify Argon2id hashes, so `PASSWORD_REHASH_ON_LOGIN` must stay `false` until
the rollback window has closed.

## 5. Backups that exist today

`backups/pre-rbac-v2/aiproject_pre_rbac.dump` (taken before RBAC work) and a `volumes/` folder; older
dumps under `backups/phase21`, `backups/phase22`. All are ignored by Git. Take a **fresh** backup at
gate G3, because production data may have changed since.

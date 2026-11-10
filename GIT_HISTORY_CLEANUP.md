# Git History Cleanup Runbook (prepared, NOT executed)

> **Nothing in this file has been run.** It rewrites public history and force-pushes. Run it only
> after you approve, in the order below. Read "Limits" first: a rewrite cannot undo the exposure
> that already happened.

## Why

The public repository `Mehak-991/AI-ML-Project-` contains database backups that were committed and
pushed. Each holds the administrator's email, a password hash (PBKDF2-SHA256, 29,000 rounds), hashed
refresh tokens, and dataset/model/job metadata. At the time of the audit the hash was **identical to
the live admin's current hash**.

| Commit | Date | Paths (all under `backups/`) |
|---|---|---|
| `e62825c` | 2026-10-31 | `db_backup_aiproject_20261030_212154.sql.gz` (+ `.meta.json`, `.sha256`) |
| `93ce598` | 2026-11-01 | `db_backup_aiproject_20261031_191321.sql.gz` (+ `.meta.json`, `.sha256`) |
| `c007d64` | 2026-11-03 | removal from the tree (the files remain in earlier commits) |

The files are not tracked now, but they remain in history and on GitHub.

## Step 0 — Rotate the admin password FIRST (before any rewrite)

History cleanup is pointless while the exposed password still works. Do this through the running
application (sign in, change password), or ask for it to be done. A password change also revokes that
account's refresh tokens. After the change the old hash in history no longer protects anything.
Pick a new password that was never used elsewhere. Also decide whether the exposed admin **email**
(personal data) matters to you.

Also confirm nothing else in `.env` was ever committed: the audit found none, and the JWT secret and
database password are **not** in history, so they do not need rotating because of this leak.

## Step 1 — Mirror backup (so you can always go back)

```powershell
cd C:\Users\HP\Desktop
git clone --mirror https://github.com/Mehak-991/AI-ML-Project-.git aiproject-mirror-backup.git
# Keep this folder OFFLINE and private. It still contains the dumps by design.
git -C aiproject-mirror-backup.git count-objects -vH
```

Do not push from or to this mirror.

## Step 2 — Rewrite in a fresh clone (never in your working copy)

Everything is already pushed (`main` equals `origin/main` when this was prepared), so a fresh clone
contains all current work. If you have commits that are not pushed, push them normally first.

```powershell
cd C:\Users\HP\Desktop
git clone https://github.com/Mehak-991/AI-ML-Project-.git aiproject-clean
cd aiproject-clean

# Preview what will be removed (read-only):
git log --all --name-only --format= -- backups | Sort-Object -Unique

pip install git-filter-repo        # already installed on this machine
git filter-repo --invert-paths --path-glob "backups/db_backup_aiproject_*"
```

`filter-repo` also removes the `origin` remote on purpose. Verify before pushing:

```powershell
git log --all --oneline -- backups                   # must print nothing
git rev-list --objects --all | Select-String "backups/"   # must print nothing
git count-objects -vH
# Secret scan of the rewritten history (values redacted):
docker run --rm -v "${PWD}:/repo:ro" --entrypoint sh ghcr.io/gitleaks/gitleaks:v8.30.0 -c "git config --global --add safe.directory /repo && gitleaks git /repo --redact=100 --no-banner --exit-code 1"
```

Also check the working tree still builds and the unit tests still pass in this clone.

## Step 3 — Force-push (point of no return for the public history)

```powershell
git remote add origin https://github.com/Mehak-991/AI-ML-Project-.git
git push --force-with-lease origin main
# Only if you use tags:  git push --force origin --tags
```

If branch protection blocks the force-push, temporarily allow it in the repository settings and
restore the protection immediately afterwards.

## Step 4 — Make your working copy match (do NOT use `git pull`)

Your current working folder still has the old history. The safest fix is to move it aside and
re-clone, because `git reset --hard` would discard any uncommitted work in it:

```powershell
cd C:\Users\HP\Desktop
Rename-Item "ss_AIML _project" "ss_AIML _project.old"
git clone https://github.com/Mehak-991/AI-ML-Project-.git "ss_AIML _project"
# Copy back what git does not track (never committed): .env, .venv312, datasets, uploads, trained_models, backups
```

Keep `.old` until you have confirmed the Docker stack still starts from the new folder. Docker Compose
names its project after the folder; the project name is fixed to `aiproject` in `compose.yaml`, so the
existing volumes keep working. Do not run `docker compose down -v` during any of this.

## Step 5 — After the push

1. Everyone with a clone or fork must re-clone. Old clones still contain the dumps.
2. **GitHub keeps the old objects reachable** by commit SHA, in forks, in open or closed pull-request
   refs (`refs/pull/*`) and in cached views, even after a force-push. Ask GitHub Support to run a
   garbage collection and to remove cached views and any sensitive-data references. If the repository
   was forked, the forks are outside your control.
3. Enable GitHub secret scanning and push protection in the repository settings.
4. CI already scans history with gitleaks and rejects tracked dumps, env files and keys
   (`secret-scan` job). The scanner does **not** recognise a database dump, so
   `scripts/check_tracked_files.py` is the control that would have caught this.

## Limits (be honest with yourself about these)

- The dumps were public from 2026-10-31. Treat the admin password hash and email as compromised
  forever; the rotation in Step 0 is what protects the account, not the rewrite.
- A rewrite changes every commit hash after `e62825c`, breaking links, open pull requests, and
  anyone's local clone.
- Third parties may already hold copies (clones, forks, caches, archives). That cannot be checked
  from here.

## Alternative if you prefer not to rewrite

Rotate the password (Step 0), accept that the old hash is public but now worthless, and rely on the
new CI guard to prevent a repeat. This is a legitimate choice when the repository holds no other
sensitive history; the email address and the dataset/model metadata in the dumps remain public.

## Rollback

Before Step 3: delete `aiproject-clean`; nothing has changed anywhere. After Step 3: restore with
`git push --force origin refs/heads/main` from the mirror
(`git -C aiproject-mirror-backup.git push --force https://github.com/Mehak-991/AI-ML-Project-.git main`).
That republishes the dumps, so do it only if the rewrite itself was wrong.

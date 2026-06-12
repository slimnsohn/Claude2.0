# Windows setup (PostgreSQL 16, native — no Docker)

Recorded from the actual install on 2026-06-12. Docker is deliberately not
used: the DB must be available for scheduled ingest without Docker Desktop
running. `docker-compose.yml` remains as an alternative for other machines.

## 1. PostgreSQL 16 via winget

```powershell
winget install --id PostgreSQL.PostgreSQL.16 --source winget `
  --override "--mode unattended --unattendedmodeui none --superpassword <PW> --serverport 5432 --enable-components server,commandlinetools --disable-components pgAdmin,stackbuilder"
```

- `--override` replaces ALL installer defaults — the string must be complete.
- Installs to `C:\Program Files\PostgreSQL\16\`. `psql.exe` is **not** on PATH;
  use the full path `C:\Program Files\PostgreSQL\16\bin\psql.exe`.
- Service `postgresql-x64-16` runs automatically at boot.
- The superuser password is stored in `.env` as `PGSUPERPASSWORD`.

## 2. Role, databases, schema

```powershell
$psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"
$env:PGPASSWORD = "<superpw>"
& $psql -U postgres -h localhost -c "CREATE ROLE resmap LOGIN PASSWORD 'resmap';"
& $psql -U postgres -h localhost -c "CREATE DATABASE resmap OWNER resmap;"
& $psql -U postgres -h localhost -c "CREATE DATABASE resmap_test OWNER resmap;"

$env:PGCLIENTENCODING = "UTF8"   # schema.sql is UTF-8; Windows psql defaults WIN1252
& $psql -v ON_ERROR_STOP=1 -f db\schema.sql "postgresql://resmap:resmap@localhost:5432/resmap"
& $psql -v ON_ERROR_STOP=1 -f db\schema.sql "postgresql://resmap:resmap@localhost:5432/resmap_test"
```

**Gotcha:** Windows psql stops option parsing at the first positional argument
— flags (`-v`, `-f`) MUST come before the connection URL or they are silently
ignored (it prints only a "extra command-line argument ignored" warning).

`resmap_test` is truncated by integration tests; never point it at real data.

## 3. Python

```powershell
python -m venv .venv               # Python 3.13
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests\ -q          # all green before working
```

## 4. Venue credentials

- **Polymarket, Gemini, Kalshi market data: no credentials needed.** All three
  ingest publicly (verified live 2026-06-12 — Kalshi /markets is public; RSA
  signing is only for private endpoints).
- Optional Kalshi signing (higher rate limits / private endpoints later):
  regenerate at kalshi.com → account → API keys, save the private key to
  `secrets/kalshi_private.pem`, set `KALSHI_API_KEY_ID` in `.env`.

## 5. LLM (rule parser)

`claude -p` CLI must be on PATH (it is: `~/.local/bin/claude`). No API key.
Model defaults to `sonnet` via `CLAUDE_CLI_MODEL` in `.env`.

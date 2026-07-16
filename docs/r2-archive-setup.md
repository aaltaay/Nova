# Cloudflare R2 archive setup (Nova OS P8)

Nova can upload finished cold-archive days to **Cloudflare R2** as content-addressed
objects. Upload is **opt-in** and **fail-loud**: missing keys never look like success.

## Secrets — `.env` only

Put credentials in the local `.env` (never commit them):

```env
# Cloudflare R2 (Nova OS P8 cold-archive durability)
ARCHIVE_R2_ENABLED=false
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
# Optional override (default: nova-archive)
#R2_BUCKET=nova-archive
```

| Variable | Purpose |
|----------|---------|
| `ARCHIVE_R2_ENABLED` | Must be `true` to attempt uploads |
| `R2_ACCOUNT_ID` | Cloudflare account id (endpoint host) |
| `R2_ACCESS_KEY_ID` | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_BUCKET` | Optional; defaults to `nova-archive` (`R2_BUCKET_DEFAULT`) |

Object keys use prefix `nova-os/archive/` (`R2_PREFIX`) + sha256 path.

## Create bucket + token (user action)

1. Cloudflare dashboard → **R2** → Create bucket (e.g. `nova-archive`).
2. Manage R2 API Tokens → Create token with Object Read & Write on that bucket.
3. Copy Account ID + Access Key ID + Secret into `.env` as above.
4. `pip install boto3` in the backend env (optional dependency; status reports loudly if missing).
5. Set `ARCHIVE_R2_ENABLED=true`.
6. Compact a finished day (maintenance loop or `compact_day`), then upload:
   - Python: `from archive.r2 import upload_day; upload_day("YYYY-MM-DD")`
   - Or enable `ARCHIVE_MAINTENANCE_ENABLED=true` so the hourly loop compacts + uploads.

## Health

`GET /api/archive/health` reports:

- `configured` / missing env (loud)
- last verified remote day, lag, calendar gaps, bytes / object estimates
- `require_verified_before_trim: true` — hot L2 timer purge stays blocked until remote verify

CLI: `py tools/nova_os_replay.py health`

## Trim policy

`ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM` remains **True**. Unverified hot data is never
timer-purged. Successful R2 upload marks the day in `archive_cold/_r2_verified.json`.

## Restore runbook

See Obsidian note: `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Archive-Restore-Runbook.md`.

---

## Phase C remainder — Bucket Lock + token rotation (user console steps)

Agents **cannot** click Cloudflare console for you. Complete these manually, then record the date in `Nova-Roadmap-Status.md`.

### R2 Bucket Lock (object immutability)

1. Cloudflare dashboard → **R2** → open bucket `nova-archive` (or your `R2_BUCKET`).
2. **Settings** → **Bucket Lock** (or Object Lock / retention — name varies by Cloudflare UI).
3. Enable a lock rule that prevents overwrite/delete of archived objects for your retention window (Nova cold days under prefix `nova-os/archive/`).
4. Save. Confirm a test overwrite of a known object key is rejected (or document that lock applies only to new writes if that is Cloudflare’s model).
5. Record in Roadmap-Status: date enabled + retention days.

**Honesty:** Do not mark Bucket Lock `[x]` until you have completed the console steps. Code cannot assert console lock state.

### Rotate temporary / test R2 API token

1. Cloudflare → **R2** → **Manage R2 API Tokens**.
2. Create a **new** token with Object Read & Write limited to the Nova archive bucket.
3. Update local `.env` only (never commit):
   - `R2_ACCESS_KEY_ID=`
   - `R2_SECRET_ACCESS_KEY=`
4. Restart the API process so `load_dotenv` picks up new values.
5. Verify: `GET /api/archive/health` still shows configured; optionally `upload_day` for a test day.
6. **Revoke/delete** the old temporary token in the Cloudflare UI.
7. Record rotation date in Roadmap-Status (no secret values).

### First real compacted day + `walk_day` / restore

Prerequisites: market capture produced hot `bars_1m` (or tape + bars) for a finished session date.

```text
# Compact finished day (from backend env)
py -3 -c "from archive.compact import compact_day; print(compact_day('YYYY-MM-DD'))"

# Optional R2 upload when ARCHIVE_R2_ENABLED=true
py -3 -c "from archive.r2 import upload_day; print(upload_day('YYYY-MM-DD'))"

# Restore round-trip into temp SQLite
py -3 -c "from archive.restore import restore_day_to_temp; print(restore_day_to_temp('YYYY-MM-DD'))"

# No-hindsight walk
py tools/nova_os_replay.py walk YYYY-MM-DD
# or: GET /api/archive/walk/YYYY-MM-DD
```

**Current blocker (2026-07-15):** local `backend/.cache/archive_cold/` has **no** compacted `YYYY-MM-DD` directories. Hot store may have tape-only days without `bars_1m`. Phase C remainder stays `[~]` until the first real compact + walk evidence is recorded — do not invent a cold day.

### Evidence to paste into Roadmap-Status

| Check | Evidence |
|-------|----------|
| Bucket Lock | Console date + retention note |
| Token rotated | Date only (no keys) |
| Cold day exists | Path under `archive_cold/YYYY-MM-DD/...` |
| `restore_day_to_temp` | OK / error message |
| `walk_day` | Step count or CLI summary |

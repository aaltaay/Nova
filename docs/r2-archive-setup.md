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

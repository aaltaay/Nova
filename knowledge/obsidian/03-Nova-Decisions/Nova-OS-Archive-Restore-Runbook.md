# Nova OS Archive Restore Runbook

> Companion to [[Nova-OS-Status]] and `docs/r2-archive-setup.md` (P8).

## Goal

Recover a finished session day from cold JSONL (local) or R2 (remote) into a **temporary** SQLite for drills — never mutate live `archive.db` blindly.

## Local restore drill

```text
# From backend/ with PYTHONPATH=.
py -c "from archive.restore import restore_day_to_temp; print(restore_day_to_temp('YYYY-MM-DD'))"
```

Expect `ok: true`, matching `expected` / `actual` row counts, empty `mismatches`.

Cold layout:

```text
<cache>/archive_cold/<YYYY-MM-DD>/<ARCHIVE_SCHEMA_VERSION>/<table>.jsonl
<cache>/archive_cold/<YYYY-MM-DD>/<ARCHIVE_SCHEMA_VERSION>/<table>.manifest.json
```

## R2 restore (when keys configured)

1. Confirm `GET /api/archive/health` → `r2.configured: true` and a `last_verified_day`.
2. Download content-addressed objects by sha256 from manifests (keys under `nova-os/archive/objects/…`).
3. Place files under the cold layout above and re-run `restore_day_to_temp`.

Never treat a missing HeadObject / failed put as success — `archive.r2` refuses to mark verified.

## Trim / purge

Do **not** enable hot trim while `ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM` is True and days are unverified. P8 keeps this gate on by default.

## Replay after restore

```text
py tools/nova_os_replay.py replay YYYY-MM-DD --json
py tools/nova_os_replay.py review YYYY-MM-DD
```

Replay calls `nova_os.decide(..., record=False)` — no receipts, no orders.

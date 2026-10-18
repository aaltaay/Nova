"""The builders of the Massive-derived research datasets: ``trades_flow_v1`` (one row per ticker-minute of trade flow),
``trades_movers_v1`` (every raw trade of each day's movers), ``quotes_movers_v1`` (every NBBO quote of the same
movers), the reference archive under ``store/reference`` (news, corporate actions, short data, financial
statements, ratios and float, month by month from 2016), and the raw-file verification (``verified.jsonl``,
``verify_all.json``). Research tooling: nothing in ``backend/`` imports it and nothing here places an order.

The other research stores have their own builders: ``research/orb`` (``orb.duckdb``, ``seconds.duckdb``, the
minute / day flat-file download and the first reference dump) and ``research/bb_mr`` (``bb_mr.duckdb``).
``docs/massive-builders.md`` lists every output with its columns.

The modules run as scripts from the repo root (``py -3 research/massive_builders/<name>.py``) and import each other
by putting this folder on ``sys.path``, the way they ran beside each other before they moved here:

  massive_env.py        paths and credentials from the environment (nothing touches the disk at import)
  massive_bucket.py     the flat-file bucket: S3 client, listing, ranged download, gzip check, verified.jsonl
  massive_jobs.py       run control shared by every job: log, STOP file, priority, memory hold, one copy at a time
  trades_products.py    the day's movers and the two trades products (the flow and movers SQL)
  massive_archive.py    the trades archive: room policy, the per-day job, the plan and its supervisor (CLI)
  raw_verify.py         `massive_archive.py verify`: every whole raw file read through gzip once
  quotes_archive.py     the quotes archive: quotes_v1 raw files and quotes_movers_v1 (CLI)
  reference_archive.py  every non-flat-file dataset, month by month (CLI)
  reference_status.py   what the reference archive holds: `reference_archive.py status` and the download page rows
  massive_access.py     whether Massive still serves its files (access.json) (CLI)
  disk_scan.py          which raw files and derived tables are whole on disk
  verify_all.py         the end-to-end check from 2016 to today (verify_all.json) (CLI)
  massive_inventory.py  what the bucket holds, sizes only (CLI)

Paths and credentials come from the environment: ``NOVA_MARKET_DATA_DIR`` (default ``E:\\Nova\\massive``),
``NOVA_EDGE_LAB_DIR`` (the research lab's extra ticker lists, default ``F:\\Nova\\private\\edge-lab``),
``NOVA_ENV_PATH`` (default the repo's ``.env``) holding ``MASSIVE_S3_ACCESS_KEY_ID`` /
``MASSIVE_S3_SECRET_ACCESS_KEY`` / ``MASSIVE_S3_ENDPOINT`` / ``MASSIVE_API_KEY``; a process environment variable
of the same name wins over the file. No credential is ever printed.
"""

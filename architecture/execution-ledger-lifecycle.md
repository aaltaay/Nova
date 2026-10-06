# Execution ledger connection lifecycle (#748)

The owner is `backend/execution/ledger_conn.py`. This is the connection-reuse
contract beneath ADR 007's execution ledger and ADR 010's off-loop FIFO
persistence. Cleanup must never close SQLite while another thread uses it.

## Lease and retirement

- Acquiring a kept connection, recording its active lease, and registering it
  for cleanup form one atomic transition. Cleanup cannot observe a registered
  connection before its lease is recorded.
- A logical `close()` keeps the lease active through rollback. Only after
  rollback finishes may the connection become idle or close physically.
- `close_all()` atomically retires all registered connections. Idle connections
  close immediately; an active connection remains physically open until its
  owning caller finishes its logical `close()`. Cleanup does not wait on that
  caller's SQL or rollback and never executes SQLite against its active lease.
- A retired connection is never reused. An active outer lease still causes a
  nested use to obtain a fresh, unkept connection. The next use after the outer
  lease ends opens a new kept connection.
- Normal idle reuse, per-thread ownership, rollback on logical close, path/file
  identity changes and dropping a broken rollback remain unchanged. SQLite's
  WAL durability and commit boundaries remain unchanged.

The lifecycle lock protects ownership transitions; it does not span a caller's
SQL or rollback. IB callbacks continue to enqueue persistence and return; this
change adds no broker call, spending gate or blocking persistence on the IB loop.

## Test isolation and verification

The autouse operator-isolation fixture drains execution persistence before
changing its temporary paths and before cleanup restores those paths or closes
the ledger connections. A drain timeout fails the test explicitly. Test files
are temporary; no reproduction reads or writes the operator's database.

Deterministic regressions use the actual persistence queue, pausing an active
lease before a write or during rollback while another thread requests cleanup.
The write must commit; rollback must finish without a closed-database error;
retired connections must close only after their owner returns them. Existing
reuse, nesting, replacement and broken-rollback checks stay in force. Related
validation includes ledger generations, execution latency, receipts and the
Orders Today blotter, followed by the backend suite.

The trigger was PR #745's Python 3.13 CI segfault: an ack update in the
persistence worker overlapped autouse teardown physically closing that
connection. A temporary-only subprocess also reproduced an active connection
being invalidated and its queued write being lost on the current master.

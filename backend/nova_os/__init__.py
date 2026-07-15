"""
Nova OS — Nova's auditable trading decision + operations layer.

Phase P1 (this module today) is the *audit foundation* only:
  - `codes`      — the stable vocabulary (decision verdicts, control modes,
                   action codes, reason codes), policy-version metadata, and
                   the temporary loss policy. Pure, no state.
  - `events_db`  — append-only SQLite schema + connection for the event log.
  - `events`     — append/read helpers and the no-silent-action receipt builder.

No decision logic (`decide()`) lives here yet — that arrives in P2. Nothing in
this package places, modifies, or cancels an order; it only records receipts.
"""

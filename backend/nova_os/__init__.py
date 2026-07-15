"""
Nova OS — Nova's auditable trading decision + operations layer.

  P1 — audit foundation:
    codes / events_db / events — vocabulary + append-only receipts
  P2 — decide() brain (signal only):
    gates / decide — ordered BUY|WAIT|NO_BUY with receipts; no orders
  P3 — Decision UX + operator visibility (frontend / CLI)
  P4 — Confirm mode + emergency controls:
    control_mode / staged_tickets — signal|confirm staging, kill/flatten;
    executor routes Approve/Reject; auto_* not selectable until P5

P4 still never auto-places: confirm only stages; Approve calls the executor.
"""

"""
Nova OS — Nova's auditable trading decision + operations layer.

  P1 — audit foundation:
    codes / events_db / events — vocabulary + append-only receipts
  P2 — decide() brain (signal only):
    gates / decide — ordered BUY|WAIT|NO_BUY with receipts; no orders

Nothing in this package places, modifies, or cancels an order.
"""

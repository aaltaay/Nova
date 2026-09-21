"""Nova's practice account engine (ADR 020): Paper on the live feed, Sim on a replay.

Never places to IBKR. ``practice.broker.for_venue`` hands out the venue's
broker -- Paper trades the live reference on the persistent ledger, Sim trades
the loaded replay on a scratch, event-sourced one -- and ``sim.broker`` is a
thin facade over the Sim instance so every existing caller keeps working.
Fees and margin follow ``architecture/practice-account.md``; fill rules follow
``architecture/practice-fills.md``.
"""

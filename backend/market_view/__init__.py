"""What the operator's screen shows of the market, how fresh it is, and the order gate that refuses a stale view (ADR 045).

- ``versions``: each symbol's Level 2 book and quote carry a version (``seq``, ``at``), with
  history, so the gate can tell when any version the desk showed was replaced.
- ``viewer_queues``: the per-viewer hand-off from the IB thread to a socket's loop -- the
  newest book only (never a backlog) or a print FIFO -- with a thread-safe, coalesced wake-up.
- ``gate``: refuses a desk order priced from a view that lags (``VIEW_STALE``), arrived late
  (``ORDER_LATE``), while Nova itself is behind the feed (``FEED_STALE``), or without its view
  (``VIEW_MISSING``).
"""

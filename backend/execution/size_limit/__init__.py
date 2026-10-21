"""Your own order size limit on Paper and Sim: shares per order and dollars at risk to its stop (ADR 064).

Settings > Loss limits holds it beside the daily loss limit, one pair of numbers per practice venue,
each optional and off until the operator types it (``settings``). The execution door asks ``gate``
before a hand order that opens or adds to a position; a refusal says the limit in words. Selling what
is held, covering a short, cancels, Flatten, KILL and every bot order never meet it; Live keeps its own
cap (``execution.qty_gate``). Schema: ``architecture/schema/execution.md``.
"""

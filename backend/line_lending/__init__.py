"""Level 2 and Time & Sales lines lent by hidden Trader tabs to the setups Nova may buy (ADR 044 decision 6).

When a setup of a strategy at On, on a stock whose Buy is Nova, is armed, near its
trigger or in a trade, and no depth line is free, the lines of a Trader tab no visible
window shows are lent to it -- its Level 2 line, and its AllLast line with it, since
IBKR counts tick-by-tick lines like depth lines: the tab says so and waits, and both
lines come back when the setup ends, its trade ends, the tab comes to the front, or
lending is switched off. Nothing here places, stages or cancels an order.

loans.py (the loans and the tick), loan.py (one loan: its words and audit lines),
loan_tape.py (a loan's AllLast line, said when down and asked again), borrowers.py (who
may borrow), lines.py (which lines may be lent), line_moves.py (moving them), focus.py
(which tabs are in front), sockets.py (which sockets are Trader tabs'), socket_gate.py
(what a socket meets), setting.py (the switch in bot-session.json), view.py and
routes.py (``GET /api/ibkr/depth/lines``, ``PATCH /api/ibkr/depth/lending``).
"""

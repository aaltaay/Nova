"""Level 2 lines lent by hidden Trader tabs to the setups Nova may buy (ADR 043 decision 6).

When a setup of a strategy at On, on a stock whose Buy is Nova, is armed, near its
trigger or in a trade, and no depth line is free, the line of a Trader tab no
visible window shows is lent to it: the tab says so and waits, and the line comes
back when the setup ends, its trade ends, the tab comes to the front, or lending is
switched off. Nothing here places, stages or cancels an order.

loans.py (the loans and the tick), borrowers.py (who may borrow), lines.py (moving a
line), focus.py (which tabs are in front), sockets.py (which sockets are Trader
tabs'), setting.py (the switch in bot-session.json), view.py and routes.py
(``GET /api/ibkr/depth/lines``, ``PATCH /api/ibkr/depth/lending``).
"""

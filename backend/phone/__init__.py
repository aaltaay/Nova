"""The phone's own door (ADR 070, amendment 2026-11-10): the PIN that unlocks it and its orders.

Owns: the phone PIN's check and lockout (``pin``), the one unlocked session (``session``), and the
``/api/phone`` routes (``routes``) -- the only writes the request guard lets another device make.

It owns no order logic and no arming rule. Every order it takes is handed to the desk's own route
handlers (``routes.trading_execution``) naming the venue the operator tapped on, so it passes the
same door and the same gates as an order from the desk, and the door refuses it if the desk has
moved. The padlock is the desk's (``ibkr.safety.arm``): on Live it opens only with the Live PIN
(amendment 2026-11-20).
"""

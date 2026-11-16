"""The phone's own door (ADR 070, amendment 2026-11-10): the PIN that unlocks it and its Paper-only orders.

Owns: the phone PIN's check and lockout (``pin``), the one unlocked session (``session``), and the
``/api/phone`` routes (``routes``) -- the only writes the request guard lets another device make.

It owns no order logic. Every order it takes is handed to the desk's own route handlers
(``routes.trading_execution``) naming Paper as its venue, so it passes the same door and the same
gates as an order from the desk, and the door refuses it if the desk is anywhere else.
"""

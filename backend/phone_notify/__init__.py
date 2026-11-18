"""Notifications to the operator's phone (ADR 070, amendment 2026-11-18): what is sent, when, and the sending.

Owns: the phone's notification settings and its subscribed phones (``store``, ``phone-notify.json``), the PC's
sending key (``vapid``, one line of the desk's ``.env``), the rule that decides whether one event becomes a
notification (``gate``, pure), the words of each notification (``words``, pure), Web Push's message format
(``webpush``, pure) and its sending (``sender``), the one entry the desk's own producers call
(``hooks``), and the ``/api/phone/notify`` routes (``routes``).

It watches; it never trades. A notification is words and the screen a tap opens: nothing in this package
places, changes or cancels an order, arms the desk, or grants a stock to anyone. It also decides nothing
about the market: an alert, a setup's stage, a fill and the loss limit's marks are the desk's own, handed
over by the module that owns each (``alerts.hooks``, ``setup_scanner``, ``hot_list``, ``practice``,
``execution``, ``loss_limit``).

The sending runs on a thread of its own, so no producer waits for a push service. A failure here is logged
and kept for the phone's Notifications screen (``last_sent``); it never reaches the producer that called.
"""

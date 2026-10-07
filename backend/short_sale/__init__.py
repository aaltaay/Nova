"""Short selling: the one short check every venue runs, and its margin (ADR 048).

Every short entry -- the ticket, a hotkey, the bot, Auto-entry, Approve, the localhost bot API --
on Live, Paper and Sim passes the same rules, run by the execution door under its lock
(``execution.service``) and read by the screens that show them. ``margin`` is the published
margin and the liquidation price (pure); ``door`` is the check the execution door runs.

Owns no persisted state.
"""

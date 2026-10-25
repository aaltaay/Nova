"""The Market page (ADR 053): the day's market health at a glance -- read-only, every price IBKR's.

``state`` holds each read's last answer and who is looking; ``clock`` the session; ``contracts`` and
``ibkr_reads`` ask IBKR (cold snapshots, paced bars, one scan, contract details); ``breadth`` samples NYSE's
indicators; ``holdings`` reads State Street's SPDR files; ``calendar`` the day's events; ``industries`` each
runner's IBKR category; ``climate`` the small-cap climate from the leaderboard store; ``temperature`` its day /
week / month labels; ``sectors`` the boards and
top stocks; ``day_read`` the verdict's rules; ``board`` the wire; ``jobs`` what each background reader reads
and how often; ``refresh`` runs them, warm while nobody looks; ``keep`` keeps their answers across restarts;
``routes`` the HTTP surface. Nothing here places an order or feeds a scanner, chart, HOD Momo, setup lane or bot.
"""

"""The Global page (ADR 060): where the world's stock money went today, measured from each market's own trades.

``markets`` knows each market's hours in its own time zone; ``flows`` turns IBKR's bars into money in and out
(pure); ``contracts`` and ``reads`` ask IBKR (a line held for a moment, paced bars, last in line); ``state`` holds each
read's last answer; ``refresh`` runs the reads on each market's clock; ``keep`` keeps their answers across restarts;
``board`` composes the wire; ``routes`` the HTTP surface. Nothing here places an order or feeds a scanner, chart, HOD
Momo, setup lane, bot or the Market page.
"""

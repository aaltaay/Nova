"""LULD price bands: Nova's calculation of each stock's limit up / limit down (ADR 047).

IBKR passes on the halt, never the band, so Nova applies the published Limit Up-Limit Down rules
to the tape and the NBBO it holds. ``rules.py`` holds the Plan's numbers, ``tracker.py`` one
stock's reference-price state machine (both pure), ``live.py`` the worker that feeds the live
lines, ``replay.py`` a Session Record's, ``views.py`` the wire shape, ``ladder.py`` the Level 2
socket frames and ``routes.py`` the route. ``study.py`` and ``records.py`` measure it against the
exchanges' own bands (``tools/luld_check.py``). Read-only: nothing here places, gates or cancels
an order.
"""

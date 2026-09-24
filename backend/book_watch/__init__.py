"""The book watcher (ADR 031): which resting Level 2 size was filled and which was pulled.

Follows every held depth line with its tape, off the IB loop, and flags large
pulls, pulls as the price came toward the size, and repeats -- hints
consistent with spoofing, never a detection. Read-only: nothing here places,
gates or cancels an order. See detector.py (pure), live.py (the worker),
journal.py, replay.py and view.py.
"""

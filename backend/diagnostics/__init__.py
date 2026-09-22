"""Desk diagnostics: a checklist of facts, never a verdict (ADR 021).

``collect*.py`` are pure collectors (inputs in, rows out). ``gather.py`` is
the one imperative shell that reads live modules. ``routes.py`` serves
``GET /api/diagnostics`` and ``GET /api/diagnostics/bundle``.
"""

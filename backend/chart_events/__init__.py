"""Earnings reports and stock splits marked on the daily charts (operator ask, 2026-10-12).

``earnings.py`` turns a registrant's SEC EDGAR filings into earnings events and ``splits.py`` turns
Yahoo's split history into split events (both pure); ``reader.py`` fetches them in the background and
keeps them in memory; ``routes.py`` answers ``GET /api/chart-events/{symbol}``, cut at the desk's
clock. Display only: nothing places, sizes or gates on an event.
"""

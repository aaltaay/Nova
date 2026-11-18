"""Constants of the brain's Nasdaq book (ADR 072 Amendment 5, ``ibkr.venue_book``).

The brain's lane also reads one exchange's own book: asked on the exchange itself, never SMART, so
``isSmartDepth`` is False there. It takes one of the login's Level 2 lines (``IBKR_MAX_DEPTH_SYMBOLS``) only while
one is free. IBKR sent 20 rows a side for 20 asked (2026-11-18).
"""
IBKR_VENUE_BOOK_EXCHANGE = "NASDAQ"
IBKR_VENUE_BOOK_ROWS = 20
IBKR_VENUE_BOOK_RETRY_SEC = 15.0   # after a refusal, before the book is asked for again

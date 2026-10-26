"""The Congress page (ADR 066): what members of Congress reported trading, read from their own filings.

``house_pdf`` and ``senate_html`` read one report each (pure); ``trades`` derives a trade's kind, side, gift, range
and lag (pure); ``matching`` ties a filer to a member; ``store`` keeps reports and trades (SQLite); ``consent`` keeps
the operator's one-time agreement to the reports' use rule; ``roster`` and ``photos`` keep the members, their
committees and portraits; ``house`` and ``senate`` read the two official sites; ``state`` holds each source's status;
``refresh`` runs the reader; ``board`` and ``views`` compose the wire; ``routes`` the HTTP surface. Read-only: nothing
here places an order or feeds a scanner, chart, HOD Momo, setup lane or bot, and no price here comes from anywhere
but IBKR's own bars on the page.
"""

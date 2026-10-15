"""Followed traders: another program's feed of traders' positions, priced with Nova's IBKR data (read-only).

On only when ``NOVA_FOLLOW_FEED_URL`` names the feed (``config``); unset, nothing here is registered or asks
anything. ``feed`` reads the feed's day and its trades across days, ``lines`` holds Level 1 lines for open
positions, ``exits`` reads the tape at each exit in the background and keeps it, ``tickers`` checks a ticker the
feed may have read glued to its price against that tape at the entry, ``pricing`` is the per-share arithmetic,
``scoring`` the win / loss / scratch / unscored rule and ``view`` puts the answers together. Nothing here places an order or feeds a scanner row, a chart, HOD Momo, a setup lane or a bot.
Schema: architecture/schema/followed-traders.md.
"""

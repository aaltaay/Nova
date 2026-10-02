"""Today's hot list (ADR 044): the stocks Nova watches all day and may trade.

Fed by the leaders rule's top N on the live Gainers board and by the operator's star, up to
``HOT_LIST_CAP``, fresh at 04:00 ET. Listed names are followed by the setup scanners; Nova buys
only listed stocks whose Buy is Nova (the stock's own Who trades switch, ADR 037).

``store`` is the file; ``service`` every write (and the 04:00 rollover); ``auto`` the leaders feed;
``nova_buys`` the Nova Buy sides a rollover or a removal takes back; ``stock_tie`` the Who trades
tie-in; ``following`` whether the scanners follow a listed name and why not (the list shares HOD Momo's
reserved slots with Former Momo); ``view`` and ``routes`` serve ``/api/hot-list``.
"""
from hot_list.store import entries_on, is_listed, listed_or_unread, listed_symbols, trading_day

__all__ = ["entries_on", "is_listed", "listed_or_unread", "listed_symbols", "trading_day"]

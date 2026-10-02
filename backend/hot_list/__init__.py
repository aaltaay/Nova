"""Today's hot list (ADR 043): the stocks Nova watches all day and may trade.

Fed by the leaders rule's top N on the live Gainers board and by the operator's star, up to
``HOT_LIST_CAP``, fresh at 04:00 ET. Listed names are followed by the setup scanners; Nova buys
only listed stocks whose Buy is Nova (the stock's own Who trades switch, ADR 037).
"""
from hot_list.store import entries_on, is_listed, listed_symbols, trading_day

__all__ = ["entries_on", "is_listed", "listed_symbols", "trading_day"]

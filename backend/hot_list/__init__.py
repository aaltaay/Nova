"""Today's hot list (ADR 044, amended 2026-10-06): the stocks Nova watches all day.

Fed by the leaders rule's top N on the live Gainers board (``auto``, an auto star) and by the operator's
star, up to ``HOT_LIST_CAP``, fresh at 04:00 ET. Listed names are followed by the setup scanners. The list
never decides who trades a stock, and nobody buys from it (ADR 072: the strategies only watch).

``store`` is the file; ``service`` every write (and the 04:00 rollover); ``auto`` the leaders feed;
``following`` whether the scanners follow a listed name and why not (the list shares HOD Momo's reserved
slots with Former Momo); ``view`` and ``routes`` serve ``/api/hot-list``.
"""
from hot_list.store import entries_on, is_listed, listed_symbols, trading_day

__all__ = ["entries_on", "is_listed", "listed_symbols", "trading_day"]

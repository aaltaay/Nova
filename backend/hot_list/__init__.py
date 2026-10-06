"""Today's hot list (ADR 044, amended 2026-10-06): the stocks Nova watches all day.

Fed by the leaders rule's top N on the live Gainers board (``auto``, an auto star) and by the operator's
star, up to ``HOT_LIST_CAP``, fresh at 04:00 ET. Listed names are followed by the setup scanners. The list
never decides who trades a stock: that is the stock's own Buy / Sell switch (ADR 037), and starring or
taking a star off never changes it.

``store`` is the file (and ``day_reset_block``: the bot buys nothing until today's 04:00 reset has run);
``service`` every write (and the 04:00 rollover, which also resets yesterday's bot buys); ``auto`` the
leaders feed; ``nova_buys`` the reset itself; ``following`` whether the scanners follow a listed name and
why not (bot-buy stocks, then the list, share HOD Momo's reserved slots with Former Momo); ``view`` and
``routes`` serve ``/api/hot-list``.
"""
from hot_list.store import day_reset_block, entries_on, is_listed, listed_symbols, trading_day

__all__ = ["day_reset_block", "entries_on", "is_listed", "listed_symbols", "trading_day"]

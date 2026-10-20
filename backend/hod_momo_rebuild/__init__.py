"""A rebuilt day's HOD Momo alerts: the real engine replayed over a Massive-rebuilt Sim day (ADR 023 amendment 2026-10-14).

``watch`` picks, minute by minute, the stocks live HOD Momo would have watched (``hod_momo_active.build_active_set``
over that minute's rebuilt boards); ``daily`` reads each one's facts as of the day from Massive's day bars and its
float from the SEC shares outstanding filed before the day; ``ticks`` turns the day's trades into the L1 ticks IBKR
would have sent; ``engine`` feeds them through ``hod_momo.on_trade_update`` on the replay clock; ``run`` is one
build, ``store`` owns the per-day files, ``job`` starts and watches a build from the API, ``worker`` is the build's
own process, ``batch`` builds a range of days one after another and ``playback`` answers the history route. Rules:
``architecture/schema/scanner.md``, "A rebuilt day's HOD Momo alerts".
"""

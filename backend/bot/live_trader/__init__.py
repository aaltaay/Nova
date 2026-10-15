"""The Live Trader bot (ADR 055): a TraderTV host's bar, copied on Paper -- one bot per host, never Live.

Owner: the host bots' settings (``live-trader-bots.json``, ``settings``) and what they hold
(``live-trader-book.json``, ``book``). ``answer`` reads the feed through ``followed_traders`` (the page's own
sightings, closes on leaving and ticker check); ``feed_rows`` and ``rules`` are the pure reading of a host's
rows and the checks before a step; ``decide`` compares one answer with the last and says what to send, skip or
ask, with no clock or I/O of its own; ``orders`` sends through the execution door (ADR 007, origin
``live_trader``) and reads Paper's ledger; ``lines`` holds the bot's Level 1 lines (``ibkr.ticks``); ``market``
reads quotes and market caps; ``watcher`` is the backend loop that ties them; ``view`` and ``routes`` serve the
Bots page. Schema: architecture/schema/bot.md ("The Live Trader bot").
"""

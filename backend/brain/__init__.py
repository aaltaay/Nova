"""The brain's door: the third trader's own way to name its stock and send its orders on Paper (ADR 072 decision 10).

Owns the brain's session (one program on this PC: its claim, heartbeat, note, reading list and events), the limits
that are the brain's alone before the execution door (``rules``), what it sends (``orders``: a long bracket, a stop
move, a cancel, a close -- every one stamped origin ``brain``), Nova's own close at the brain's flat-by time
(``watcher``) and ``/api/brain`` (``routes``). Its lane is ``line_lanes.brain``; its book, switch and limits are
``owners`` and ``traders``. Shapes: ``architecture/schema/bot.md`` "The brain's door".

The brain never trades Live: ``execution.venue_door`` refuses any ``brain`` send there, and this door refuses off
Paper.
"""

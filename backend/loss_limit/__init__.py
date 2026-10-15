"""The daily loss limit: one dollar line for every account, yours and the bots' trades alike (ADR 056).

Settings > Loss limits holds it: the dollars, Warn me, No new buys and Auto sell
(``settings``). Each account counts its trades opened today (``count``, ``accounts``), and
the watcher (``watch``) warns, stops new buys or sells what was opened today once the loss
stays past the line for 10 seconds. The execution door asks ``gate`` before any order that
opens or adds to a position. Schema: ``architecture/schema/loss-limit.md``.
"""

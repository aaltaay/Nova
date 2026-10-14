"""A rebuilt day's Gappers by the second: built from the Massive trades, read at the Sim playhead (ADR 023 amendment 2026-10-13).

``build`` is the pure core (who can be on the list inside a minute, the list at a second), ``run`` is one build, ``inputs`` reads the
stored rebuilt day and the Massive files, ``store`` owns the per-day files, ``job`` starts and watches a build from
the API, ``worker`` is the build's own process and ``playback`` answers the route. Rules:
``architecture/schema/scanner.md``, "A rebuilt day's Gappers by the second".
"""

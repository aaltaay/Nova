"""Performance recorder (ADR 026): who used the time, not only how late it was.

Measures and never acts. Entry points: :mod:`perf.runtime` (start / stop from
the lifespan), :mod:`perf.routes` (``/api/perf/*``), :mod:`perf.counters`
(drop counters the hot paths bump).
"""

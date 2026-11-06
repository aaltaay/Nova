"""Claude's seat on the desk (ADR 068): one AI trader on Paper -- its seat and lease, the Level 2 line it
holds locked, its Paper-only orders, the close when it goes quiet or the day ends, and what the desk shows of it.

Owner of ``/api/agent/trader``. Every send goes through ``execution.service`` like the Live Trader bot's (ADR 055);
nothing here sends to Live.
"""

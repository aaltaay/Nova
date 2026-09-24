"""The bot's read on one stock (ADR 035): the plan, the seven signal groups, the day's decisions and
the history for one symbol, composed from the owners that already hold each fact.

Read-only: nothing here places, stages or cancels an order, opens an IBKR line or waits on the
network. ``gather`` reads the owners (caches, stores, sensors); ``indicators``, ``plan`` and the
``rows_*`` modules are pure rules over what it gathered; ``routes`` serves them.
"""

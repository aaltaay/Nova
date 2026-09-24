"""Nova's own first-pullback bot (ADR 030): it trades the template in play's first pullbacks on Paper and Sim.

Owner: the bot's trade -- the ``trade`` key of ``bot-session.json``
(``bot.persist``, schema 4, an optional key; absent before the first trade).
``runner`` is the loop and the trade's state machine; ``orders`` sends through
``execution.service.execute`` with source ``bot`` and reads the venue's orders,
positions and quotes. Nothing here places on Live.
"""

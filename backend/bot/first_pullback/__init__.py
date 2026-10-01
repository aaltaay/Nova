"""Nova's own bot (ADR 030, ADR 042): it trades the go triggers of every setup at Strategy on Paper and Sim.

Owner: the bot's trade -- the ``trade`` key of ``bot-session.json``
(``bot.persist``, an optional key; absent before the first trade). ``runner`` is the
loop and the trade's state machine; ``admit`` the rules a go trigger meets (shared with
Auto-entry); ``orders`` sends through ``execution.service.execute`` with source ``bot``
(the entry is a practice bracket) and reads the venue's orders, positions and quotes;
``handover`` lets go of the trade when the operator takes the exit or the desk leaves
the venue. Nothing here places on Live.
"""

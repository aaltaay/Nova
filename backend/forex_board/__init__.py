"""The Forex page (ADR 061): the whole currency market's size, and what each of its 19 biggest currencies did today.

``clock`` knows the FX day (17:00 to 17:00 New York, Sunday to Friday) and each city's session; ``prices`` turns IBKR's
spot midpoints into each currency's move and strength (pure); ``money`` turns a CME future's bars into money in and
out (pure); ``contracts`` and ``reads`` ask IBKR (a line held for a moment, paced bars, last in line); ``state`` holds
each read's last answer; ``jobs`` and ``refresh`` run the reads on the FX day's clock; ``keep`` keeps their answers
across restarts; ``board`` and ``rows`` compose the wire; ``routes`` the HTTP surface. The market's size is the BIS
survey's, labelled; nothing here places an order or feeds a scanner, chart, HOD Momo, setup lane, bot, or the Market
or Global page.
"""

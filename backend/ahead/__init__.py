"""Ahead (ADR 061): the forecast zone on the Trader's 1-minute chart -- the private forecaster's answer, served.

``config`` reads the forecaster's loopback address and token from ``.env``. ``inputs`` takes the completed 1-minute
bars, the desk clock and the prior close from Nova's own readers. ``client`` is the only HTTP caller (contract
``ahead-forecaster/1``) and parses its answers strictly. ``view`` builds the wire answer
(``architecture/schema/ahead.md``). ``service`` caches and single-flights it. ``routes`` serves ``/api/ahead/*``.

Nova's own lines carried on to where they meet, the walls, the wall-first and "if it triggers" odds and the MACD fan
are worked out on the desk (``frontend/src/ahead/``) from this answer, the stock read and the chart's candles: nothing
here reads the stock read. A chart study: nothing here places, stages, sizes, delays or blocks an order, and nothing
feeds a scanner row, a setup or a bot. The forecaster gets bars only from Nova and reads no market data itself.
"""

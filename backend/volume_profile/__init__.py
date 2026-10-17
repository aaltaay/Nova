"""Volume profile on the Trader's 5-minute chart (ADR 058): today's and yesterday's profiles from IBKR 1-minute bars.

``profile`` builds one (pure), ``service`` reads the bars and answers ``GET /api/volume-profile/{symbol}``
(``routes``), ``ibkr_minutes`` is its one IBKR request. A chart study: nothing here places or blocks an order.
"""

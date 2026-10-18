"""Bollinger Bands mean-reversion research harness for U.S. stocks (Phase L research).

Owns the pre-registered protocol, causal universe construction (Liquid Reference Universe A
and Morning Active Universe B), completed-candle Bollinger Band signal engine, shared-account
basket/risk/cash-reservation portfolio simulator, IBKR fee + bid/ask/participation/halt
execution model, NBBO tick-level validator, and walk-forward/stress-test runner.
Nothing in backend/ imports this package, and nothing here places live or paper broker orders.
"""
from __future__ import annotations

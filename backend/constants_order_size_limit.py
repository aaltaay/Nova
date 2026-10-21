"""The order size limit's constants (ADR 064, ``architecture/schema/execution.md``).

Your own hand orders on Paper and Sim: at most so many shares, and at most so many dollars at risk to
the order's stop. Off on both venues until you type a number in Settings > Loss limits -- this file
holds the rules for a number, never a default one.
"""
from __future__ import annotations

ORDER_SIZE_LIMIT_FILE = "order-size-limit.json"     # the operator's setting, in the operator cache
ORDER_SIZE_LIMIT_SCHEMA_VERSION = 1

ORDER_SIZE_LIMIT_VENUES = ("paper", "sim")          # Live keeps IBKR_QTY_CAP (execution/qty_gate.py)
ORDER_SIZE_LIMIT_FIELDS = ("max_shares", "max_risk_usd")
ORDER_SIZE_LIMIT_MIN_SHARES = 1
ORDER_SIZE_LIMIT_MAX_SHARES = 1_000_000
ORDER_SIZE_LIMIT_MIN_RISK_USD = 1                   # whole dollars
ORDER_SIZE_LIMIT_MAX_RISK_USD = 1_000_000

ORDER_SIZE_LIMIT_API_PATH = "/api/order-size-limit"

# Reason codes on the wire.
ORDER_SIZE_LIMIT_REASON_SHARES = "ORDER_SIZE_LIMIT_SHARES"
ORDER_SIZE_LIMIT_REASON_RISK = "ORDER_SIZE_LIMIT_RISK"
ORDER_SIZE_LIMIT_REASON_NO_STOP = "ORDER_SIZE_LIMIT_NO_STOP"
ORDER_SIZE_LIMIT_REASON_UNREADABLE = "ORDER_SIZE_LIMIT_UNREADABLE"
ORDER_SIZE_LIMIT_REASON_INVALID = "ORDER_SIZE_LIMIT_INVALID"

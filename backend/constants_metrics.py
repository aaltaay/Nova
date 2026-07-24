"""Authoritative tunables for lightweight operation latency metrics."""

# Recent successful and failed durations retained per operation. Aggregate
# count/error_count remain process-lifetime totals; percentiles use this window.
OP_METRICS_RING_SIZE = 512

# The legacy top-level health RTT is an Alpaca account API probe, while Nova's
# market-data surfaces are IBKR-only. Keep attribution explicit in API payloads.
HEALTH_SOURCE_ALPACA_ACCOUNT = "alpaca_account_api"
HEALTH_LATENCY_SOURCE_ALPACA_ACCOUNT = "alpaca_account_http"

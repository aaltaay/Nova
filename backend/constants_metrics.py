"""Authoritative tunables for lightweight operation latency metrics."""

# Recent successful and failed durations retained per operation. Aggregate
# count/error_count remain process-lifetime totals; percentiles use this window.
OP_METRICS_RING_SIZE = 512

# Top-level /api/health status is Nova process liveness (not Alpaca, not IBKR).
# IBKR session SoT is /api/ibkr/status. Alpaca account RTT is no longer the API chip.
HEALTH_SOURCE_NOVA_PROCESS = "nova_process"
HEALTH_LATENCY_SOURCE_NONE = "none"
# Legacy labels kept for tests / old cached payloads that may still appear once.
HEALTH_SOURCE_ALPACA_ACCOUNT = "alpaca_account_api"
HEALTH_LATENCY_SOURCE_ALPACA_ACCOUNT = "alpaca_account_http"

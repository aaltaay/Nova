"""IBKR discovery / movers adapter — never falls back to Alpaca prices."""
from __future__ import annotations

from ibkr import discovery as _ibkr_discovery
from ibkr_bridge import IbkrBridgeError, run_ibkr


def _run_scanner(coro, *, label: str) -> list[dict]:
    """Run IB discovery coro; surface failures (never silent [])."""
    try:
        raw = run_ibkr(coro, on_error="raise", label=label)
    except IbkrBridgeError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize for runners
        raise IbkrBridgeError(f"{label}: {exc!r}") from exc
    if raw is None:
        raise IbkrBridgeError(f"{label} bridge returned None")
    return list(raw)


class IbkrScannerAdapter:
    """Implements ``DiscoveryPort`` + ``MoversPort`` for discovery=ibkr."""

    def get_gappers(self) -> list[dict]:
        return _run_scanner(_ibkr_discovery.get_gappers(), label="gappers")

    def get_gainers(self) -> list[dict]:
        return _run_scanner(_ibkr_discovery.get_gainers(), label="gainers")

    def get_losers(self) -> list[dict]:
        return _run_scanner(_ibkr_discovery.get_losers(), label="losers")

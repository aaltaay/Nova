"""IBKR discovery / movers adapter — never falls back to Alpaca prices."""
from __future__ import annotations

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


def _lease_owned(table: str) -> IbkrBridgeError:
    return IbkrBridgeError(
        f"{table} roster is lease-owned (ADR 008 + ADR 010 decision 5): names come "
        "from the persistent reqScannerSubscription and prices from L1. One-shot "
        "discovery must not write a second roster."
    )


class IbkrScannerAdapter:
    """``DiscoveryPort`` + ``MoversPort`` shape for discovery=ibkr.

    Every method refuses. The persistent scanner stream
    (``ibkr/scanner_stream.py``) is the only roster owner while discovery is
    IBKR; premarket Gappers is projected from Gainers by
    ``ibkr/gapper_view.py``. Two owners racing on one Gateway socket is what
    wedged the IB loop on 2026-07-29, and the surviving one-shot code kept
    attracting fixes it could never deliver (2026-08-24). Failing loud here
    beats a silent second writer.
    """

    def get_gappers(self) -> list[dict]:
        raise _lease_owned("gappers")

    def get_gainers(self) -> list[dict]:
        raise _lease_owned("gainers")

    def get_losers(self) -> list[dict]:
        raise _lease_owned("losers")

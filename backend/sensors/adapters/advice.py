"""News / catalyst sensor -- wired to the Advice feature only."""
from __future__ import annotations

from typing import Any

from sensors.envelope import build_envelope

_STANCE_SENTIMENT = {
    "LONG": "bullish",
    "SHORT": "bearish",
    "HOLD": "neutral",
}


def _transcript_text(run: dict[str, Any], agent: str) -> str | None:
    for event in run.get("transcript") or []:
        if not isinstance(event, dict):
            continue
        if event.get("type") != "message":
            continue
        if str(event.get("agent") or "") != agent:
            continue
        text = str(event.get("content") or "").strip()
        if text:
            return text
    return None


def read_news(symbol: str) -> dict[str, Any]:
    from advise.service import AdviseError, latest

    try:
        run = latest(symbol)
    except AdviseError as exc:
        return build_envelope(
            sensor="news",
            symbol=symbol,
            status="live",
            data={"source": "advice"},
            error=str(exc),
        )
    if not run:
        return build_envelope(
            sensor="news",
            symbol=symbol,
            status="live",
            data={"source": "advice", "run": None},
            error="No Advice run for this symbol. Open Advice and Run -- this sensor does not call Finnhub.",
        )
    result = run.get("result") or {}
    stance = str(result.get("stance") or "").upper() or None
    headline = _transcript_text(run, "news")
    if not headline:
        reasons = result.get("reasons") or []
        headline = str(reasons[0]) if reasons else None
    sentiment = _STANCE_SENTIMENT.get(stance or "", None)
    return build_envelope(
        sensor="news",
        symbol=symbol,
        status="live",
        data={
            "source": "advice",
            "headline": headline,
            "sentiment_text": _transcript_text(run, "sentiment"),
            "timestamp": run.get("finished_ts") or run.get("created_ts"),
            "sentiment": sentiment,
            "stance": stance,
            "run_id": run.get("id"),
            "run_status": run.get("status"),
            "stale": run.get("stale"),
            "note": "Wired to Advice (/api/advise). Not Advisor. Not a news API.",
        },
    )

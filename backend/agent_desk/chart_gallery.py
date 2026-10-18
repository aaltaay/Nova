"""Immutable generic historical chart data for Nova's native renderer."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .chart_gallery_data import ET, annotations, bars, identity, label, shape


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_five(rows: list[dict]) -> list[dict]:
    """Only five consecutive observed minute starts form a wall-clock candle."""
    groups: dict[int, list[dict]] = {}
    for bar in rows:
        epoch = int(datetime.fromisoformat(bar["t"]).timestamp())
        groups.setdefault(epoch // 300 * 300, []).append(bar)
    result = []
    for start, group in sorted(groups.items()):
        expected = [start + n * 60 for n in range(5)]
        if [int(datetime.fromisoformat(r["t"]).timestamp()) for r in group] != expected:
            continue
        result.append(dict(t=group[0]["t"], o=group[0]["o"], h=max(r["h"] for r in group),
                           l=min(r["l"] for r in group), c=group[-1]["c"], v=sum(r["v"] for r in group)))
    return result


def _json_file(path: Path, maximum_bytes: int) -> bytes:
    with path.open("rb") as stream:
        blob = stream.read(maximum_bytes + 1)
    if len(blob) > maximum_bytes:
        raise ValueError("Chart input exceeds byte bound")
    return blob


def load_gallery(selection: Path, expected_sha256: str) -> dict:
    began = time.perf_counter()
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("Selection SHA256 must contain64 hex characters")
    selection = selection.resolve()
    raw_bytes = _json_file(selection, 2 * 1024 * 1024)
    if hashlib.sha256(raw_bytes).hexdigest() != expected_sha256.lower():
        raise ValueError("Selection SHA256 mismatch")
    raw = shape(json.loads(raw_bytes), {"schema_version", "kind", "family", "selected"})
    if (raw["schema_version"] != 1 or isinstance(raw["schema_version"], bool)
            or raw["kind"] != "historical_ohlcv" or not label(raw["family"], 80)
            or not isinstance(raw["selected"], list) or not 1 <= len(raw["selected"]) <= 9):
        raise ValueError("Expected a version1 generic historical chart selection")
    entries, identities, aggregation_ms = [], [], 0.0
    for index, entry in enumerate(raw["selected"]):
        shape(entry, {"day", "ticker", "annotations", "bar_projection"}, {"as_of_m"})
        identities.append(identity(entry))
        notes = annotations(entry["annotations"])
        reference = shape(entry["bar_projection"], {"path", "sha256"})
        if not isinstance(reference["path"], str) or not Path(reference["path"]).is_absolute():
            raise ValueError("Projection path must be absolute")
        projection_path = Path(reference["path"]).resolve()
        if projection_path.parent != selection.parent / "bars":
            raise ValueError("Projection path outside selection bars directory")
        blob = _json_file(projection_path, 2 * 1024 * 1024)
        if hashlib.sha256(blob).hexdigest() != reference["sha256"]:
            raise ValueError("Projection SHA256 mismatch")
        one = bars(json.loads(blob), entry)
        before = time.perf_counter()
        five = aggregate_five(one)
        aggregation_ms += (time.perf_counter() - before) * 1000
        item = dict(id=index, symbol=entry["ticker"], date=entry["day"], annotations=notes,
                    bars_1m=one, bars_5m=five,
                    source=dict(selection_sha256=expected_sha256.lower(), projection_sha256=reference["sha256"]))
        if "as_of_m" in entry:
            boundary = datetime.fromisoformat(entry["day"]).replace(tzinfo=ET) + timedelta(minutes=entry["as_of_m"])
            item.update(as_of_m=entry["as_of_m"], as_of_t=boundary.astimezone(timezone.utc).isoformat())
        entries.append(item)
    if identities != sorted(set(identities)):
        raise ValueError("Frozen selection identities must be unique and chronological")
    return dict(schema_version=1, kind="historical_ohlcv", family=raw["family"],
                selection_sha256=expected_sha256.lower(), entries=entries,
                timings=dict(load_ms=(time.perf_counter() - began) * 1000, aggregation_ms=aggregation_ms))


def create_app(selection: Path, expected_sha256: str, frontend_origin: str,
               instance: str = "manual-preview") -> FastAPI:
    """Explicit immutable inputs; no trading app, environment, or credential imports."""
    gallery = load_gallery(selection, expected_sha256)
    body = json.dumps(gallery, allow_nan=False, separators=(",", ":")).encode()
    app = FastAPI(title="Nova frozen historical chart gateway")
    app.add_middleware(CORSMiddleware, allow_origins=[frontend_origin], allow_methods=["GET"])

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "testclient"):
            return Response(status_code=403)
        return await call_next(request)

    @app.get("/api/agent/chart-gallery")
    def read_gallery() -> Response:
        return Response(body, media_type="application/json", headers={
            "X-Nova-Chart-Instance": instance,
            "ETag": '"' + expected_sha256.lower() + '"', "Cache-Control": "no-store"})

    return app

"""Export one local historical ticker/day through Nova's existing native gateway.

Usage: python tools/nova_historical_charts.py export --symbol DEMO --date 2022-02-01
  --massive-root LOCAL_MINUTE_ROOT --gateway-root APPROVED_NOVA --output NEWDIR
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from nova_historical_resolver import HistoricalChartError, local_path, resolve_bundle

EXPORT_TIMEOUT_SECONDS = 180


def export_historical(*, symbol: str, day: str, output: Path, massive_root: Path,
                      gateway_root: Path, samples: int = 0) -> dict[str, Any]:
    """Trusted roots are operator configuration; only symbol/day select data."""
    began = time.perf_counter()
    if isinstance(samples, bool) or not isinstance(samples, int) or not 0 <= samples <= 50:
        raise HistoricalChartError("invalid_samples", "Samples must be an integer from 0 through 50")
    gateway = local_path(gateway_root)
    script = local_path(gateway / "tools" / "nova_charts.py")
    if not gateway.is_dir() or not script.is_file() or not script.is_relative_to(gateway):
        raise HistoricalChartError("gateway_unavailable", "The approved checkout has no offline chart exporter")
    receipt = resolve_bundle(massive_root, symbol, day, output)
    image_output = Path(receipt["selection_path"]).parent / "images"
    command = [sys.executable, str(script), "export", "--selection", receipt["selection_path"],
               "--sha256", receipt["selection_sha256"], "--output", str(image_output), "--samples", str(samples)]
    export_began = time.perf_counter()
    try:
        process = subprocess.run(command, cwd=gateway, capture_output=True, text=True, check=False,
                                 timeout=EXPORT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        def captured_text(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""

        failure = {"ok": False, "error": "export_timeout", "timeout_seconds": EXPORT_TIMEOUT_SECONDS,
                   "stdout": captured_text(error.stdout), "stderr": captured_text(error.stderr)}
        with (image_output.parent / "native_export_failure.json").open("x", encoding="utf-8") as stream:
            json.dump(failure, stream, indent=2, sort_keys=True)
            stream.write("\n")
        raise HistoricalChartError("export_timeout", "Native export exceeded 180 seconds; the bundle and local logs are preserved") from error
    if process.returncode:
        raise HistoricalChartError("export_failed", "The native Nova exporter failed; the frozen local bundle is preserved")
    try:
        native = json.loads(process.stdout)
    except (TypeError, ValueError) as error:
        raise HistoricalChartError("export_failed", "The native Nova exporter returned an invalid JSON receipt") from error
    if not isinstance(native, dict) or native.get("ok") is not True:
        raise HistoricalChartError("export_failed", "The native Nova exporter did not confirm successful capture and cleanup")
    result = {"ok": True, "schema_version": 1, "kind": "historical_ohlcv",
              "bundle": receipt, "native_export": native,
              "image_output": str(image_output),
              "timings": {"resolve_freeze_ms": receipt["resolve_freeze_ms"],
                          "native_export_wall_ms": (time.perf_counter() - export_began) * 1000,
                          "total_wall_ms": (time.perf_counter() - began) * 1000}}
    with (image_output.parent / "historical_export.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--massive-root", type=Path, required=True)
    parser.add_argument("--gateway-root", type=Path, required=True)
    parser.add_argument("--samples", type=int, choices=range(51), default=0)
    args = parser.parse_args(argv)
    try:
        result = export_historical(symbol=args.symbol, day=args.date, output=args.output,
                                   massive_root=args.massive_root, gateway_root=args.gateway_root,
                                   samples=args.samples)
    except HistoricalChartError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

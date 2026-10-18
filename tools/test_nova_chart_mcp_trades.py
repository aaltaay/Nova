"""The trade-list MCP call: explicit roots only, the trades root checked first, verified PNGs back; no browser."""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

import nova_chart_mcp as M

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aR1cAAAAASUVORK5CYII=")
TRADE = {"symbol": "DEMO", "date": "2020-01-02", "entry_time": "09:30:05", "entry_price": 2.0,
         "exit_time": "09:30:40", "exit_price": 2.1}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def fake_export(output: Path, names: list[str]) -> None:
    output.mkdir()
    write_json(output / "selection.json", {"selected": [{} for _ in names]})
    image_dir = output / "images/images"
    image_dir.mkdir(parents=True)
    images = []
    for name in ["NOVA_HISTORICAL_OVERVIEW", *names, "NOVA_GATEWAY_VIEW"]:
        (image_dir / f"{name}.png").write_bytes(PNG)
        images.append(str(image_dir / f"{name}.png"))
    capture = image_dir / "CAPTURE_VERIFICATION.json"
    write_json(capture, {"errors": [], "blocked_requests": []})
    digest = M.sha256(output / "selection.json")
    native = {"ok": True, "schema_version": 1, "selected_count": len(names), "owned_trees_stopped": True,
              "owned_children_stopped": True, "active_owned_processes": 0, "cleanup_errors": [],
              "source_data_mutated": False, "broker_or_desk_calls": False, "selection_sha256": digest,
              "images": images, "image_sha256": {Path(p).name: M.sha256(Path(p)) for p in images},
              "capture_verification": str(capture)}
    write_json(output / "images/EXPORT_RECEIPT.json", native)
    write_json(output / "historical_export.json", {
        "schema_version": 1, "ok": True, "kind": "historical_ohlcv", "native_export": native,
        "bundle": {"selection_path": str(output / "selection.json"), "selection_sha256": digest,
                   "selected_count": len(names)}})


class TradeCharts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        for name in ("resolver/tools", "gateway/tools", "minute", "massive/trades_v1", "output"):
            (self.base / name).mkdir(parents=True)
        for rel in ("resolver/tools/nova_historical_charts.py", "resolver/tools/nova_trade_charts.py",
                    "gateway/tools/nova_charts.py", "gateway/tools/nova_chart_processes.py"):
            (self.base / rel).write_text("# fixture", encoding="utf-8")
        self.roots = M.Roots.checked(*(self.base / n for n in ("resolver", "gateway", "minute", "output")),
                                     self.base / "massive")
        self.calls = []

        def execute(args, cwd, gateway, cancel, timeout):
            self.calls.append(args)
            fake_export(Path(args[args.index("--output") + 1]), ["01_DEMO_2020-01-02_10s"])
            return M.Execution(0, True, 0)
        self.service = M.ChartService(self.roots, execute)

    def test_a_trade_list_runs_the_trade_front_door_with_explicit_roots(self):
        result = self.service.export_trades([TRADE], "r32-trades", bar_seconds=10, before_s=60, after_s=30)
        self.assertTrue(result["ok"], result)
        [args] = self.calls
        self.assertTrue(args[2].endswith("nova_trade_charts.py"))
        self.assertEqual(json.loads(args[args.index("--trades-json") + 1]), [TRADE])
        self.assertEqual(args[args.index("--massive-root") + 1], str(self.base / "massive"))
        self.assertEqual(args[args.index("--gateway-root") + 1], str(self.base / "gateway"))
        for flag, value in (("--bar-seconds", "10"), ("--before", "60"), ("--after", "30")):
            self.assertEqual(args[args.index(flag) + 1], value)
        checked, data = M.verified_inline_image(result, self.roots.output)
        self.assertTrue(checked["ok"])
        self.assertEqual(data, PNG)

    def test_bad_requests_refuse_before_any_process(self):
        for trades, extra, code in (("not a list", {}, "TRADES_INVALID"), ([], {}, "TRADES_INVALID"),
                                    ([TRADE] * 51, {}, "TRADES_INVALID"), ([TRADE], {"bar_seconds": 60},
                                                                           "BAR_SECONDS_INVALID"),
                                    ([TRADE], {"before_s": -1}, "WINDOW_INVALID")):
            self.assertEqual(self.service.export_trades(trades, "x", **extra), {"ok": False, "error": {"code": code}})
        self.assertEqual(self.calls, [])

    def test_a_massive_root_without_trades_refuses(self):
        (self.base / "massive/trades_v1").rmdir()
        result = self.service.export_trades([TRADE], "x")
        self.assertEqual(result, {"ok": False, "error": {"code": "TRADES_ROOT_MISSING"}})

    def test_an_older_resolver_without_the_trade_front_door_refuses(self):
        (self.base / "resolver/tools/nova_trade_charts.py").unlink()
        result = self.service.export_trades([TRADE], "x")
        self.assertEqual(result, {"ok": False, "error": {"code": "TRUSTED_ENTRYPOINT_MISSING"}})


if __name__ == "__main__":
    unittest.main()

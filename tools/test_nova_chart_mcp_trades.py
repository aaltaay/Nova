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


def fake_export(output: Path, names: list[str], warm_pid: int | None = None) -> None:
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
    if warm_pid is not None:
        for key in ("owned_trees_stopped", "owned_children_stopped", "active_owned_processes"):
            del native[key]
        native.update(renderer="warm", warm_service={"pid": warm_pid, "owned_pids": [11, 12],
                                                     "live_owned_processes": 5, "jobs_served": 1})
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

    def warm_service(self, ensure, receipt_pid):
        renderers = []

        class Renderer:
            idle_seconds = 600

            def __init__(self, gateway, python):
                self.gateway, self.python = gateway, python
                renderers.append(self)

            def ensure(self):
                return ensure()

        def execute(args, cwd, gateway, cancel, timeout):
            self.calls.append(args)
            warm = receipt_pid if "--warm" in args else None
            fake_export(Path(args[args.index("--output") + 1]), ["01_DEMO_2020-01-02_10s"], warm)
            return M.Execution(0, True, 0)
        service = M.ChartService(self.roots, execute, warm=Renderer)
        self.assertEqual(renderers[0].gateway, self.base / "gateway")
        return service

    def test_trade_charts_draw_with_the_servers_warm_renderer(self):
        service = self.warm_service(lambda: 4242, 4242)
        result = service.export_trades([TRADE], "warm-trades")
        self.assertTrue(result["ok"], result)
        [args] = self.calls
        self.assertEqual(args[args.index("--warm"):args.index("--warm") + 3], ["--warm", "--idle-seconds", "600"])
        self.assertEqual((result["renderer"], result["warm_renderer_pid"]), ("warm", 4242))
        self.assertIs(result["warm_renderer_started_in_call"], False)
        self.assertTrue(result["owned_tree_verified"])
        self.assertTrue(M.verified_inline_image(result, self.roots.output)[0]["ok"])

    def test_a_renderer_restarted_inside_the_call_is_reported(self):
        # The server's renderer stopped before the job (stale code, a crash), so the export started one inside the
        # call's Job; the call's verified teardown already stopped it.
        service = self.warm_service(lambda: 4242, 999)
        result = service.export_trades([TRADE], "other")
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["warm_renderer_pid"], result["warm_renderer_started_in_call"]), (999, True))

    def test_a_warm_receipt_without_its_service_or_with_cleanup_errors_is_refused(self):
        native = self.base / "output"
        for name, change in (("no-service", {"warm_service": None}), ("errors", {"cleanup_errors": ["x"]}),
                             ("mutated", {"source_data_mutated": True})):
            fake_export(native / name, ["01_DEMO_2020-01-02_10s"], 4242)
            for receipt in (native / name / "images/EXPORT_RECEIPT.json", native / name / "historical_export.json"):
                value = json.loads(receipt.read_text(encoding="utf-8"))
                (value.get("native_export", value)).update(change)
                write_json(receipt, value)
            with self.assertRaises(M.ChartError):
                M.verify_export(native / name, None, None, 0, warm_pid=4242)

    def test_a_one_shot_receipt_never_passes_as_warm_and_a_warm_one_never_as_one_shot(self):
        native = self.base / "output"
        fake_export(native / "a", ["01_DEMO_2020-01-02_10s"], 4242)
        with self.assertRaises(M.ChartError):
            M.verify_export(native / "a", None, None, 0)
        fake_export(native / "b", ["01_DEMO_2020-01-02_10s"])
        with self.assertRaises(M.ChartError):
            M.verify_export(native / "b", None, None, 0, warm_pid=4242)

    def test_no_warm_renderer_falls_back_to_the_one_shot_export_and_says_so(self):
        def unavailable():
            raise M.WarmRendererUnavailable("node is missing")
        service = self.warm_service(unavailable, 4242)
        result = service.export_trades([TRADE], "fallback")
        self.assertTrue(result["ok"], result)
        [args] = self.calls
        self.assertNotIn("--warm", args)
        self.assertEqual((result["renderer"], result["warm_error"]), ("one_shot", "WARM_RENDERER_UNAVAILABLE"))


if __name__ == "__main__":
    unittest.main()

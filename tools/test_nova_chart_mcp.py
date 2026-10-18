"""Generated-only boundary tests; optional real SDK/Job transport test is opt-in."""
from __future__ import annotations

import asyncio
import base64
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import sys
import unittest
from unittest.mock import patch

import nova_chart_mcp as M


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aR1cAAAAASUVORK5CYII=")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def make_export(output: Path, symbol="DEMO", day="2020-01-02") -> dict:
    output.mkdir()
    (output / "selection.json").write_text("{}", encoding="utf-8")
    image_dir = output / "images/images"
    image_dir.mkdir(parents=True)
    images = []
    for name in ("overview", f"01_{symbol}_{day}_1m_5m", "verification"):
        path = image_dir / f"{name}.png"
        path.write_bytes(PNG)
        images.append(str(path))
    capture = image_dir / "CAPTURE_VERIFICATION.json"
    write_json(capture, {"errors": [], "blocked_requests": []})
    digest = M.sha256(output / "selection.json")
    native = {"ok": True, "schema_version": 1, "selected_count": 1,
              "owned_trees_stopped": True, "owned_children_stopped": True,
              "active_owned_processes": 0, "cleanup_errors": [],
              "source_data_mutated": False, "broker_or_desk_calls": False,
              "selection_sha256": digest, "images": images,
              "image_sha256": {Path(p).name: M.sha256(Path(p)) for p in images},
              "capture_verification": str(capture)}
    receipt = {"schema_version": 1, "ok": True, "kind": "historical_ohlcv",
               "bundle": {"selection_path": str(output / "selection.json"),
                          "selection_sha256": digest, "symbol": symbol, "date": day,
                          "source": {"path": "PRIVATE_SOURCE_MUST_NOT_BE_RETURNED"}},
               "native_export": native, "image_output": str(output / "images")}
    write_json(output / "images/EXPORT_RECEIPT.json", native)
    write_json(output / "historical_export.json", receipt)
    return receipt


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        for name in ("resolver", "gateway", "minute", "output"):
            (self.base / name).mkdir()
        for parent, child in (("resolver", "nova_historical_charts.py"),
                              ("gateway", "nova_charts.py"),
                              ("gateway", "nova_chart_processes.py")):
            (self.base / parent / "tools").mkdir(exist_ok=True)
            (self.base / parent / "tools" / child).write_text("# fixture", encoding="utf-8")
        self.roots = M.Roots.checked(*(self.base / n for n in ("resolver", "gateway", "minute", "output")))
        self.calls = []

        def execute(args, cwd, gateway, cancel, timeout):
            self.calls.append((args, cwd, gateway, timeout))
            make_export(Path(args[args.index("--output") + 1]),
                        args[args.index("--symbol") + 1], args[args.index("--date") + 1])
            return M.Execution(0, True, 0)
        self.execute = execute
        self.service = M.ChartService(self.roots, execute)

    def call(self, **kwargs):
        request = dict(symbol="DEMO", day="2020-01-02", output_name="new-chart", samples=0)
        request.update(kwargs)
        return self.service.export(**request)

    def assert_code(self, result, code):
        self.assertEqual(result, {"ok": False, "error": {"code": code}})

    def mutate(self, change):
        def execute(*args):
            result = self.execute(*args)
            argv = args[0]
            output = Path(argv[argv.index("--output") + 1])
            receipt = json.loads((output / "historical_export.json").read_text())
            change(receipt, output)
            write_json(output / "historical_export.json", receipt)
            write_json(output / "images/EXPORT_RECEIPT.json", receipt["native_export"])
            return result
        self.service.execute = execute

    def test_success_forwards_only_explicit_roots_and_returns_verified_hashes(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.call(samples=50)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["images"]), 3)
        self.assertEqual(result["active_owned_processes"], 0)
        self.assertNotIn("PRIVATE_SOURCE", json.dumps(result))
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")
        argv, cwd, gateway, timeout = self.calls[0]
        self.assertEqual(argv[3:6], ["export", "--symbol", "DEMO"])
        self.assertEqual(argv[-4:], ["--massive-root", str(self.roots.massive),
                                    "--gateway-root", str(self.roots.gateway)])
        self.assertEqual((cwd, gateway, timeout), (self.roots.resolver, self.roots.gateway, 240))
        for image in result["images"]:
            self.assertEqual(image["sha256"], hashlib.sha256(PNG).hexdigest())

    def test_bad_tokens_do_not_launch(self):
        cases = [{"symbol": "X;whoami"}, {"symbol": ".."}, {"symbol": "é"},
                 {"symbol": "A" * 33}, {"day": "2020-1-02"}, {"day": "2020-02-30"},
                 {"output_name": "../escape"}, {"output_name": "\\\\server\\x"},
                 {"output_name": "C:other"}, {"output_name": "NUL"},
                 {"output_name": "trailing."}, {"samples": True}, {"samples": 51},
                 {"samples": -1}, {"samples": 0.5}]
        for case in cases:
            with self.subTest(case=case):
                self.assertFalse(self.call(**case)["ok"])
        self.assertEqual(self.calls, [])

    def test_exact_resolver_symbol_tokens_are_preserved(self):
        self.assertTrue(self.call(symbol="brk.b_1^X-", output_name="exact")["ok"])
        self.assertEqual(self.calls[0][0][5], "brk.b_1^X-")

    def test_impossible_calendar_date_has_specific_error(self):
        self.assert_code(self.call(day="2020-02-30"), "DATE_INVALID")

    def test_existing_output_is_preserved(self):
        target = self.roots.output / "new-chart"
        target.mkdir()
        (target / "keep").write_bytes(b"preserve")
        self.assert_code(self.call(), "OUTPUT_ALREADY_EXISTS")
        self.assertEqual((target / "keep").read_bytes(), b"preserve")
        self.assertFalse(self.calls)

    def test_roots_reject_network_relative_root_and_overlap(self):
        for value in (Path("relative"), Path("\\\\server\\share"), Path(self.base.anchor)):
            with self.subTest(path=value), self.assertRaises(M.ChartError):
                M.local_directory(value)
        with self.assertRaises(M.ChartError):
            M.Roots.checked(self.roots.resolver, self.roots.gateway,
                            self.roots.massive, self.roots.massive)

    def test_missing_entrypoint_fails_before_launch(self):
        (self.roots.resolver / "tools/nova_historical_charts.py").unlink()
        with self.assertRaisesRegex(M.ChartError, "TRUSTED_ENTRYPOINT_MISSING"):
            M.Roots.checked(self.roots.resolver, self.roots.gateway, self.roots.massive, self.roots.output)

    def test_export_runtime_is_host_selected_and_missing_runtime_refused(self):
        with self.assertRaises((M.ChartError, OSError)):
            M.ChartService(self.roots, export_python=self.base / "missing.exe")
        self.call()
        self.assertEqual(self.calls[0][0][0], str(Path(sys.executable).resolve()))

    def test_busy_never_queues_or_launches(self):
        self.service._lock.acquire()
        self.addCleanup(self.service._lock.release)
        self.assert_code(self.call(), "EXPORT_BUSY")
        self.assertFalse(self.calls)

    def test_cancel_before_launch(self):
        cancel = threading.Event()
        cancel.set()
        self.assert_code(self.call(cancel=cancel), "CANCELLED")
        self.assertFalse(self.calls)

    def test_execution_failure_and_cleanup_fail_closed(self):
        for result, code in [(M.Execution(2, True, 0), "EXPORT_FAILED"),
                             (M.Execution(0, False, None), "OWNED_CLEANUP_UNVERIFIED"),
                             (M.Execution(0, True, 1), "OWNED_CLEANUP_UNVERIFIED")]:
            self.service.execute = lambda *args: result
            self.assert_code(self.call(), code)

    def test_child_timeout_and_raw_errors_are_redacted(self):
        for error, code in [(M.ChartError("EXPORT_TIMEOUT"), "EXPORT_TIMEOUT"),
                            (RuntimeError("SECRET_TOKEN PRIVATE_PATH"), "EXPORT_UNVERIFIED")]:
            def execute(*args):
                raise error
            self.service.execute = execute
            self.assert_code(self.call(), code)

    def test_unresolved_native_cleanup_cannot_pass(self):
        self.mutate(lambda receipt, _: receipt["native_export"].update(active_owned_processes=1))
        self.assert_code(self.call(), "NATIVE_EXPORT_UNVERIFIED")

    def test_wrong_symbol_and_changed_selection_fail(self):
        self.mutate(lambda receipt, _: receipt["bundle"].update(symbol="OTHER"))
        self.assert_code(self.call(), "RECEIPT_IDENTITY_MISMATCH")
        self.mutate(lambda receipt, output: (output / "selection.json").write_text("changed"))
        result = self.call(output_name="other-chart")
        self.assert_code(result, "SELECTION_HASH_MISMATCH")

    def test_changed_image_hash_fails(self):
        self.mutate(lambda receipt, _: Path(receipt["native_export"]["images"][0]).write_bytes(PNG + b"changed"))
        self.assert_code(self.call(), "IMAGE_HASH_MISMATCH")

    def test_manifest_escape_is_never_read(self):
        outside = self.base / "private.png"
        outside.write_bytes(PNG)
        self.mutate(lambda receipt, _: receipt["native_export"]["images"].__setitem__(0, str(outside)))
        self.assert_code(self.call(), "ARTIFACT_OUTSIDE_OUTPUT")

    def test_duplicate_image_and_browser_failures_refused(self):
        self.mutate(lambda receipt, _: receipt["native_export"]["images"].__setitem__(1, receipt["native_export"]["images"][0]))
        self.assert_code(self.call(), "DUPLICATE_IMAGE")

    def test_browser_failure_is_not_hidden_by_successful_exit(self):
        def fail_browser(receipt, _):
            write_json(Path(receipt["native_export"]["capture_verification"]),
                       {"errors": ["fixture_failure"], "blocked_requests": []})
        self.mutate(fail_browser)
        self.assert_code(self.call(), "CAPTURE_UNVERIFIED")

    def test_native_receipt_must_match_embedded_copy(self):
        def execute(*args):
            result = self.execute(*args)
            receipt_path = self.roots.output / "new-chart/images/EXPORT_RECEIPT.json"
            write_json(receipt_path, {"ok": True})
            return result
        self.service.execute = execute
        self.assert_code(self.call(), "NATIVE_RECEIPT_MISMATCH")

    def test_missing_sdk_is_an_explicit_startup_block(self):
        with patch.object(M.importlib.metadata, "version", side_effect=M.importlib.metadata.PackageNotFoundError):
            with self.assertRaisesRegex(M.ChartError, "MCP_SDK_NOT_INSTALLED"):
                M.create_server(self.service)

    def test_wrong_sdk_version_is_not_silently_adopted(self):
        with patch.object(M.importlib.metadata, "version", return_value="2.0.0"):
            with self.assertRaisesRegex(M.ChartError, "MCP_SDK_VERSION_REQUIRED"):
                M.create_server(self.service)

    def test_inline_detail_uses_verified_bytes_and_preserves_metadata(self):
        body = self.call()
        result, data = M.verified_inline_image(body, self.roots.output)
        self.assertIs(result, body)
        self.assertEqual(data, PNG)
        detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
        self.assertEqual(hashlib.sha256(data).hexdigest(), detail["sha256"])

    def test_inline_changed_content_returns_fixed_error_and_preserves_verified_export(self):
        body = self.call()
        detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
        Path(detail["path"]).write_bytes(PNG + b"changed")
        result, data = M.verified_inline_image(body, self.roots.output)
        self.assertIsNone(data)
        self.assertEqual(result["error"]["code"], "INLINE_IMAGE_CHANGED")
        self.assertIs(result["verified_export"], body)

    def test_inline_oversize_is_bounded_and_does_not_return_image(self):
        body = self.call()
        detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
        Path(detail["path"]).write_bytes(M.PNG_SIGNATURE + bytes(M.MAX_INLINE_IMAGE_BYTES))
        result, data = M.verified_inline_image(body, self.roots.output)
        self.assertIsNone(data)
        self.assertEqual(result["error"]["code"], "INLINE_IMAGE_TOO_LARGE")
        self.assertIs(result["verified_export"], body)

    def test_inline_missing_and_ambiguous_detail_fail_closed(self):
        body = self.call()
        detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
        body["images"].remove(detail)
        result, data = M.verified_inline_image(body, self.roots.output)
        self.assertEqual(result["error"]["code"], "INLINE_IMAGE_MISSING")
        self.assertIsNone(data)
        body["images"].extend([detail, dict(detail)])
        result, data = M.verified_inline_image(body, self.roots.output)
        self.assertEqual(result["error"]["code"], "INLINE_IMAGE_AMBIGUOUS")
        self.assertIsNone(data)

    def test_inline_rechecks_confinement_before_open(self):
        body = self.call()
        detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
        outside = self.base / "outside_1m_5m.png"
        outside.write_bytes(PNG)
        detail["path"] = str(outside)
        result, data = M.verified_inline_image(body, self.roots.output)
        self.assertEqual(result["error"]["code"], "INLINE_IMAGE_PATH_INVALID")
        self.assertIsNone(data)


class SDKContract(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_tool_discovery_and_call(self):
        try:
            version = M.importlib.metadata.version("mcp")
        except M.importlib.metadata.PackageNotFoundError:
            self.skipTest("Optional official MCP SDK not installed")
        self.assertEqual(version, M.SDK_VERSION)
        roots = object()
        service = M.ChartService(roots)
        server = M.create_server(service)
        tools = await server.list_tools()
        self.assertEqual([tool.name for tool in tools], ["nova_historical_chart"])
        schema = tools[0].inputSchema
        self.assertEqual(set(schema["properties"]), {"symbol", "date", "output_name", "samples"})
        self.assertFalse(tools[0].annotations.openWorldHint)
        self.assertFalse(tools[0].annotations.readOnlyHint)
        self.assertEqual(tools[0].outputSchema["type"], "object")
        result = await server.call_tool("nova_historical_chart", {"symbol": "INVALID/", "date": "2020-01-02", "output_name": "new"})
        self.assertIn("SYMBOL_INVALID", str(result))

    async def test_sdk_inline_error_has_no_image_content(self):
        try:
            from mcp.types import CallToolResult
        except ImportError:
            self.skipTest("Optional official MCP SDK not installed")
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            output = base / "export"
            make_export(output)
            body = M.verify_export(output, "DEMO", "2020-01-02", 0)
            detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
            roots = M.Roots(base, base, base, base)
            service = M.ChartService(roots)
            service.export = lambda *args: body
            server = M.create_server(service)
            for data, expected in ((PNG + b"changed", "INLINE_IMAGE_CHANGED"),
                                   (M.PNG_SIGNATURE + bytes(M.MAX_INLINE_IMAGE_BYTES), "INLINE_IMAGE_TOO_LARGE")):
                Path(detail["path"]).write_bytes(data)
                result = await server.call_tool("nova_historical_chart", {
                    "symbol": "DEMO", "date": "2020-01-02", "output_name": "new"})
                self.assertIsInstance(result, CallToolResult)
                self.assertTrue(result.isError)
                self.assertEqual([c.type for c in result.content], ["text"])
                self.assertEqual(result.structuredContent["error"]["code"], expected)
                self.assertEqual(result.structuredContent["verified_export"], body)

    async def test_constructor_does_not_load_working_directory_dotenv(self):
        try:
            M.importlib.metadata.version("mcp")
        except M.importlib.metadata.PackageNotFoundError:
            self.skipTest("Optional official MCP SDK not installed")
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as name:
            try:
                os.chdir(name)
                Path(".env").write_text("FASTMCP_PORT=INVALID_GENERATED_FIXTURE\n", encoding="utf-8")
                M.create_server(M.ChartService(object()))
                self.assertEqual(Path.cwd(), Path(name))
            finally:
                os.chdir(previous)

    async def test_cancellation_waits_for_export_cleanup(self):
        try:
            M.importlib.metadata.version("mcp")
        except M.importlib.metadata.PackageNotFoundError:
            self.skipTest("Optional official MCP SDK not installed")
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            began, closed = threading.Event(), threading.Event()
            def execute(args, cwd, gateway, cancel, timeout):
                began.set()
                if not cancel.wait(5):
                    raise RuntimeError("fixture cancellation never arrived")
                closed.set()
                raise M.ChartError("CANCELLED")
            roots = M.Roots(base, base, base, base)
            service = M.ChartService(roots, execute)
            server = M.create_server(service)
            task = asyncio.create_task(server.call_tool("nova_historical_chart", {
                "symbol": "DEMO", "date": "2020-01-02", "output_name": "new"}))
            self.assertTrue(await asyncio.to_thread(began.wait, 5))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(closed.is_set())
            self.assertFalse(service._lock.locked())


@unittest.skipUnless(os.environ.get("NOVA_TEST_GATEWAY_ROOT"),
                     "Set an explicitly approved gateway checkout for real SDK/Job stdio tests")
class StdioContract(unittest.IsolatedAsyncioTestCase):
    async def test_official_sdk_round_trip_with_generated_resolver(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as name:
            base = Path(name).resolve()
            resolver, minute, output = (base / n for n in ("resolver", "minute", "output"))
            (resolver / "tools").mkdir(parents=True)
            minute.mkdir()
            output.mkdir()
            fixture = ("import sys,json,argparse\n"
                       f"sys.path.insert(0,{str(Path(__file__).resolve().parent)!r})\n"
                       "from pathlib import Path\nfrom test_nova_chart_mcp import make_export\n"
                       "p=argparse.ArgumentParser();p.add_argument('command')\n"
                       "for n in ('symbol','date','output','samples','massive-root','gateway-root'):p.add_argument('--'+n)\n"
                       "a=p.parse_args();print(json.dumps(make_export(Path(a.output),a.symbol,a.date)))\n")
            (resolver / "tools/nova_historical_charts.py").write_text(fixture, encoding="utf-8")
            params = StdioServerParameters(command=sys.executable, args=[
                "-B", str(Path(M.__file__).resolve()), "--resolver-root", str(resolver),
                "--gateway-root", os.environ["NOVA_TEST_GATEWAY_ROOT"],
                "--massive-root", str(minute), "--output-root", str(output)],
                cwd=str(base), env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
            with (base / "sdk-stderr.log").open("w", encoding="utf-8") as errors:
                async with stdio_client(params, errlog=errors) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        catalog = await client.list_tools()
                        self.assertEqual([t.name for t in catalog.tools], ["nova_historical_chart"])
                        self.assertEqual((await client.list_resources()).resources, [])
                        bad = await client.call_tool("nova_historical_chart", {
                            "symbol": "BAD/", "date": "2020-01-02", "output_name": "bad"})
                        self.assertEqual(bad.structuredContent["error"]["code"], "SYMBOL_INVALID")
                        boolean = await client.call_tool("nova_historical_chart", {
                            "symbol": "DEMO", "date": "2020-01-02", "output_name": "boolean", "samples": True})
                        self.assertTrue(boolean.isError)
                        request = {"symbol": "DEMO", "date": "2020-01-02", "output_name": "chart"}
                        result = await client.call_tool("nova_historical_chart", request)
                        self.assertFalse(result.isError)
                        body = result.structuredContent
                        self.assertTrue(body["ok"], body)
                        self.assertTrue(body["owned_tree_verified"])
                        self.assertEqual(body["active_owned_processes"], 0)
                        self.assertEqual(len(body["images"]), 3)
                        self.assertTrue(all(i["sha256"] == hashlib.sha256(PNG).hexdigest() for i in body["images"]))
                        inline = [item for item in result.content if item.type == "image"]
                        self.assertEqual(len(inline), 1)
                        self.assertEqual(inline[0].mimeType, "image/png")
                        decoded = base64.b64decode(inline[0].data, validate=True)
                        self.assertEqual(hashlib.sha256(decoded).hexdigest(), hashlib.sha256(PNG).hexdigest())
                        existing = await client.call_tool("nova_historical_chart", request)
                        self.assertEqual(existing.structuredContent["error"]["code"], "OUTPUT_ALREADY_EXISTS")
                        self.assertFalse((output / "boolean").exists())
                        self.assertFalse((output / "bad").exists())


@unittest.skipUnless(all(os.environ.get(n) for n in (
    "NOVA_TEST_GATEWAY_ROOT", "NOVA_TEST_RESOLVER_ROOT", "NOVA_TEST_EXPORT_PYTHON",
    "NOVA_TEST_ARTIFACT_ROOT")), "Explicit generated native-pipeline integration roots required")
class NativeStdioContract(unittest.IsolatedAsyncioTestCase):
    async def test_generated_parquet_through_real_sdk_resolver_and_native_renderer(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        base = Path(os.environ["NOVA_TEST_ARTIFACT_ROOT"]).resolve()
        base.mkdir(exist_ok=False)  # Keep artifacts for visual review; never reuse a run.
        minute, output = base / "minute", base / "output"
        partition = minute / "d=2020-01-02"
        partition.mkdir(parents=True)
        output.mkdir()
        generation = (
            "import duckdb,sys\n"
            "con=duckdb.connect(config={'threads':2,'memory_limit':'256MB'})\n"
            "con.execute('CREATE TABLE bars(ticker VARCHAR,m INTEGER,o DOUBLE,h DOUBLE,l DOUBLE,c DOUBLE,v DOUBLE)')\n"
            "rows=[]\n"
            "for i in range(120):\n"
            " o=20+i*.01;c=o+(.04 if i%4<2 else -.02)\n"
            " rows.append(('DEMO',540+i,o,max(o,c)+.03,min(o,c)-.03,c,1000+i))\n"
            "con.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?)',rows)\n"
            "destination=sys.argv[1].replace(\"'\",\"''\")\n"
            "con.execute(\"COPY bars TO '\"+destination+\"' (FORMAT PARQUET)\")\n"
        )
        subprocess.run([os.environ["NOVA_TEST_EXPORT_PYTHON"], "-B", "-c", generation,
                        str(partition / "part.parquet")], check=True, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        params = StdioServerParameters(command=sys.executable, args=[
            "-B", str(Path(M.__file__).resolve()),
            "--resolver-root", os.environ["NOVA_TEST_RESOLVER_ROOT"],
            "--gateway-root", os.environ["NOVA_TEST_GATEWAY_ROOT"],
            "--massive-root", str(minute), "--output-root", str(output),
            "--export-python", os.environ["NOVA_TEST_EXPORT_PYTHON"]], cwd=str(base),
            env={"PYTHONDONTWRITEBYTECODE": "1"})
        with (base / "sdk-stderr.log").open("w", encoding="utf-8") as errors:
            async with stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    self.assertEqual(len((await client.list_tools()).tools), 1)
                    result = await client.call_tool("nova_historical_chart", {
                        "symbol": "DEMO", "date": "2020-01-02", "output_name": "native", "samples": 0})
                    body = result.structuredContent
                    write_json(base / "MCP_NATIVE_RESULT.json", body)
                    self.assertFalse(result.isError)
                    self.assertTrue(body["ok"], body)
                    self.assertTrue(body["owned_tree_verified"])
                    self.assertEqual(body["active_owned_processes"], 0)
                    inline = [item for item in result.content if item.type == "image"]
                    self.assertEqual(len(inline), 1)
                    self.assertEqual(inline[0].mimeType, "image/png")
                    decoded = base64.b64decode(inline[0].data, validate=True)
                    detail = next(i for i in body["images"] if i["path"].endswith("_1m_5m.png"))
                    digest = hashlib.sha256(decoded).hexdigest()
                    self.assertEqual(digest, detail["sha256"])
                    self.assertLessEqual(len(decoded), M.MAX_INLINE_IMAGE_BYTES)
                    (base / "MCP_INLINE_DETAIL.png").write_bytes(decoded)
                    write_json(base / "MCP_INLINE_VERIFICATION.json", {
                        "image_count": len(inline), "mime_type": inline[0].mimeType,
                        "bytes": len(decoded), "sha256": digest,
                        "matches_verified_detail_manifest": True})
                    for image in body["images"]:
                        self.assertGreater(image["bytes"], 1000)
                        self.assertEqual(image["sha256"], M.sha256(Path(image["path"])))


if __name__ == "__main__":
    unittest.main()

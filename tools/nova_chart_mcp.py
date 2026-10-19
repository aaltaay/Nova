"""Optional official-SDK stdio access to bounded, stateless historical chart export.

maintainer: one-concern the MCP stdio boundary, root confinement, and export verification must live in one module
The trusted launcher supplies roots; callers supply only symbol/day/entries/output name.
No trading application imports, client configuration changes or package installs.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
from datetime import date as calendar_date
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Annotated, Any, Callable

from nova_chart_mcp_warm import WarmRenderer, WarmRendererUnavailable

SDK_VERSION = "1.26.0"
REQUEST_TIMEOUT_SECONDS = 240
MAX_RECEIPT_BYTES = 262_144
MAX_IMAGE_BYTES = 20_000_000
MAX_TOTAL_IMAGE_BYTES = 80_000_000
MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLORS = {"blue", "gold", "grey", "green", "red"}
MAX_TRADES = 50
MAX_TRADES_JSON_BYTES = 65_536
TRADE_BAR_SECONDS = {1, 5, 10, 15, 30}
DETAIL_IMAGE = re.compile(r".*_(1m_5m|\d+s)\.png\Z")


class ChartError(Exception):
    """Only these fixed error codes may cross the MCP boundary."""


def sdk_version_ok(version: str) -> bool:
    if not isinstance(version, str):
        return False
    if version == SDK_VERSION:
        return True
    match = re.fullmatch(r"1\.(\d+)\.(\d+)", version.strip())
    return bool(match and int(match.group(1)) >= 26)


def local_directory(value: Path) -> Path:
    raw = str(value)
    if raw.startswith(("\\\\", "//")):
        raise ChartError("LOCAL_ROOT_REQUIRED")
    if not value.is_absolute():
        raise ChartError("ABSOLUTE_ROOT_REQUIRED")
    if os.name == "nt":
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(value.anchor)) == 4:
            raise ChartError("LOCAL_ROOT_REQUIRED")
    for part in (value, *value.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ChartError("REPARSE_ROOT_REFUSED")
    resolved = value.resolve(strict=True)
    if not resolved.is_dir() or resolved == Path(resolved.anchor):
        raise ChartError("DEDICATED_DIRECTORY_REQUIRED")
    if str(resolved).startswith(("\\\\", "//")):
        raise ChartError("LOCAL_ROOT_REQUIRED")
    return resolved


@dataclass(frozen=True)
class Roots:
    resolver: Path
    gateway: Path
    massive: Path
    output: Path
    fallback_massive: Path | None = None

    @classmethod
    def checked(cls, resolver: Path, gateway: Path, massive: Path, output: Path,
                fallback_massive: Path | None = None) -> Roots:
        fb = local_directory(fallback_massive) if fallback_massive is not None else None
        roots = cls(*(local_directory(p) for p in (resolver, gateway, massive, output)), fb)
        sources = (roots.resolver, roots.gateway, roots.massive, *((roots.fallback_massive,) if roots.fallback_massive else ()))
        for source in sources:
            if roots.output.is_relative_to(source) or source.is_relative_to(roots.output):
                raise ChartError("OUTPUT_ROOT_OVERLAPS_INPUT")
        for base, relative in ((roots.resolver, "tools/nova_historical_charts.py"),
                               (roots.gateway, "tools/nova_charts.py"),
                               (roots.gateway, "tools/nova_chart_processes.py")):
            required = base / relative
            if not required.is_file() or not required.resolve().is_relative_to(base):
                raise ChartError("TRUSTED_ENTRYPOINT_MISSING")
        return roots


@dataclass(frozen=True)
class Execution:
    returncode: int
    trees_stopped: bool
    active_processes: int | None


def checked_executable(executable: Path) -> Path:
    if not executable.is_absolute():
        raise ChartError("EXPORT_RUNTIME_INVALID")
    parent = local_directory(executable.parent)
    info = executable.lstat()
    if os.name == "nt" and getattr(info, "st_reparse_tag", 0) == 0x8000001B:
        if not executable.is_file():
            raise ChartError("EXPORT_RUNTIME_INVALID")
        return parent / executable.name
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ChartError("EXPORT_RUNTIME_INVALID")
    resolved = executable.resolve(strict=True)
    if not resolved.is_file():
        raise ChartError("EXPORT_RUNTIME_INVALID")
    return resolved


def owned_execute(args: list[str], cwd: Path, gateway: Path,
                  cancel: threading.Event, timeout: float) -> Execution:
    """Reuse the gateway's pre-launch Job ownership; keep child logs off stdout."""
    spec = importlib.util.spec_from_file_location(
        "_nova_chart_mcp_owned", gateway / "tools/nova_chart_processes.py")
    if spec is None or spec.loader is None:
        raise ChartError("OWNERSHIP_HELPER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = module.OwnedProcesses()
    failure = None
    code = -1
    try:
        with tempfile.TemporaryFile(mode="w+b") as logs:
            process = owner.spawn(args, cwd, logs)
            deadline = time.monotonic() + timeout
            while True:
                if cancel.is_set():
                    raise ChartError("CANCELLED")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ChartError("EXPORT_TIMEOUT")
                try:
                    code = process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
    except BaseException as error:
        failure = error
    finally:
        stopped = owner.close()
    if not stopped or owner.active_processes != 0 or owner.errors:
        raise ChartError("OWNED_CLEANUP_UNVERIFIED")
    if failure is not None:
        raise failure
    return Execution(code, stopped, owner.active_processes)


def confined_file(value: Any, root: Path, max_bytes: int) -> Path:
    if not isinstance(value, str) or len(value) > 4096:
        raise ChartError("ARTIFACT_PATH_INVALID")
    path = Path(value)
    if not path.is_absolute():
        raise ChartError("ARTIFACT_PATH_INVALID")
    path = path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ChartError("ARTIFACT_OUTSIDE_OUTPUT")
    if not 0 < path.stat().st_size <= max_bytes:
        raise ChartError("ARTIFACT_SIZE_INVALID")
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_receipt(path: Path, output: Path) -> dict:
    path = confined_file(str(path), output, MAX_RECEIPT_BYTES)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChartError("RECEIPT_INVALID")
    return value


def _validate_options(as_of_m: Any, annotations: Any) -> tuple[int | None, list[dict[str, Any]] | None]:
    if as_of_m is not None and (type(as_of_m) is not int or not 0 <= as_of_m <= 1440):
        raise ChartError("AS_OF_M_INVALID")
    if annotations is None:
        return as_of_m, None
    if not isinstance(annotations, list) or len(annotations) > 32:
        raise ChartError("ANNOTATIONS_INVALID")
    cleaned: list[dict[str, Any]] = []
    for item in annotations:
        if not isinstance(item, dict) or item.get("kind") not in {"horizontal_line", "time_marker"}:
            raise ChartError("ANNOTATIONS_INVALID")
        kind = item["kind"]
        field = "price" if kind == "horizontal_line" else "minute"
        if not {"kind", field, "label"} <= item.keys() or item.keys() - {"kind", field, "label", "color"}:
            raise ChartError("ANNOTATIONS_INVALID")
        lbl = item["label"]
        if not (isinstance(lbl, str) and 1 <= len(lbl) <= 80 and lbl == lbl.strip() and all(32 <= ord(c) != 127 for c in lbl)):
            raise ChartError("ANNOTATIONS_INVALID")
        color = item.get("color", "blue")
        if not isinstance(color, str) or color not in COLORS:
            raise ChartError("ANNOTATIONS_INVALID")
        val = item[field]
        if field == "minute":
            if type(val) is not int or not 0 <= val <= 1439:
                raise ChartError("ANNOTATIONS_INVALID")
        elif isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
            raise ChartError("ANNOTATIONS_INVALID")
        cleaned.append(dict(item))
    return as_of_m, cleaned


def _verify_warm(native: dict[str, Any]) -> int:
    """A warm receipt: drawn and checked like a one-shot one, by a renderer that names itself instead of claiming
    it stopped (the call's own tree is verified by ``owned_execute``); its pid."""
    service = native.get("warm_service")
    if (native.get("ok") is not True or native.get("renderer") != "warm" or not isinstance(service, dict)
            or type(service.get("pid")) is not int or native.get("cleanup_errors") != []
            or native.get("source_data_mutated") is not False or native.get("broker_or_desk_calls") is not False):
        raise ChartError("NATIVE_EXPORT_UNVERIFIED")
    return service["pid"]


def verify_export(output: Path, symbol: str | None, day: str | None, samples: int,
                  expected_count: int = 1, warm_pid: int | None = None) -> dict[str, Any]:
    """``warm_pid``: the call asked the server's warm renderer (that pid) to draw, so only a warm receipt passes."""
    if output.resolve(strict=True) != output:
        raise ChartError("OUTPUT_DIRECTORY_CHANGED")
    receipt_path = output / "historical_export.json"
    receipt = read_receipt(receipt_path, output)
    bundle = receipt.get("bundle", {})
    native = receipt.get("native_export", {})
    if receipt.get("ok") is not True or receipt.get("schema_version") != 1 or receipt.get("kind") != "historical_ohlcv":
        raise ChartError("RECEIPT_IDENTITY_MISMATCH")
    if symbol is not None and (bundle.get("symbol") != symbol or bundle.get("date") != day):
        raise ChartError("RECEIPT_IDENTITY_MISMATCH")
    if native != read_receipt(output / "images/EXPORT_RECEIPT.json", output):
        raise ChartError("NATIVE_RECEIPT_MISMATCH")
    drew = _verify_warm(native) if warm_pid is not None else None
    if drew is None and (native.get("ok") is not True or native.get("owned_trees_stopped") is not True
            or native.get("owned_children_stopped") is not True
            or type(native.get("active_owned_processes")) is not int
            or native["active_owned_processes"] != 0 or native.get("cleanup_errors") != []
            or native.get("live_descendants_after_cleanup", 0) != 0
            or native.get("source_data_mutated") is not False
            or native.get("broker_or_desk_calls") is not False):
        raise ChartError("NATIVE_EXPORT_UNVERIFIED")
    selection = confined_file(bundle.get("selection_path"), output, MAX_RECEIPT_BYTES)
    selection_sha = sha256(selection)
    if (selection_sha != bundle.get("selection_sha256")
            or selection_sha != native.get("selection_sha256")):
        raise ChartError("SELECTION_HASH_MISMATCH")
    capture_path = confined_file(native.get("capture_verification"), output, MAX_RECEIPT_BYTES)
    capture = read_receipt(capture_path, output)
    if capture.get("errors") != [] or capture.get("blocked_requests") != []:
        raise ChartError("CAPTURE_UNVERIFIED")
    paths, hashes = native.get("images"), native.get("image_sha256")
    if (not isinstance(paths, list) or len(paths) != expected_count + 2
            or native.get("selected_count") != expected_count
            or not isinstance(hashes, dict) or len(hashes) != len(paths)):
        raise ChartError("IMAGE_MANIFEST_INVALID")
    images, seen, total = [], set(), 0
    for value in paths:
        image = confined_file(value, output, MAX_IMAGE_BYTES)
        if image in seen:
            raise ChartError("DUPLICATE_IMAGE")
        seen.add(image)
        with image.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                raise ChartError("IMAGE_FORMAT_INVALID")
        size, digest = image.stat().st_size, sha256(image)
        total += size
        if total > MAX_TOTAL_IMAGE_BYTES or digest != hashes.get(image.name):
            raise ChartError("IMAGE_HASH_MISMATCH")
        images.append({"path": str(image), "sha256": digest, "bytes": size})
    out: dict[str, Any] = {
        "ok": True, "schema_version": 1, "samples": samples, "images": images,
        "selection_sha256": selection_sha,
        "receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path)},
        "owned_tree_verified": True, "active_owned_processes": 0,
    }
    if symbol is not None and day is not None:
        out["symbol"] = symbol
        out["date"] = day
    else:
        out["selected_count"] = expected_count
    if drew is not None:
        out.update(renderer="warm", warm_renderer_pid=drew, warm_renderer_started_in_call=drew != warm_pid)
    return out


def verified_inline_image(body: dict[str, Any], approved_output: Path) -> tuple[dict[str, Any], bytes | None]:
    """Recheck only the unique verified detail (or gallery overview) image; never accept caller paths."""
    try:
        if body.get("selected_count", 1) > 1:
            candidates = [item for item in body["images"]
                          if Path(item["path"]).name == "NOVA_HISTORICAL_OVERVIEW.png"]
        else:
            candidates = [item for item in body["images"]
                          if DETAIL_IMAGE.fullmatch(Path(item["path"]).name)]
        if not candidates:
            raise ChartError("INLINE_IMAGE_MISSING")
        if len(candidates) != 1:
            raise ChartError("INLINE_IMAGE_AMBIGUOUS")
        item = candidates[0]
        try:
            path = confined_file(item["path"], approved_output, MAX_IMAGE_BYTES)
        except ChartError as error:
            raise ChartError("INLINE_IMAGE_PATH_INVALID") from error
        with path.open("rb") as stream:
            data = stream.read(MAX_INLINE_IMAGE_BYTES + 1)
        if len(data) > MAX_INLINE_IMAGE_BYTES:
            raise ChartError("INLINE_IMAGE_TOO_LARGE")
        if (not data.startswith(PNG_SIGNATURE) or len(data) != item["bytes"]
                or hashlib.sha256(data).hexdigest() != item["sha256"]
                or path.resolve(strict=True) != path):
            raise ChartError("INLINE_IMAGE_CHANGED")
        return body, data
    except ChartError as error:
        code = str(error)
    except (OSError, ValueError, TypeError, KeyError):
        code = "INLINE_IMAGE_UNAVAILABLE"
    return {"ok": False, "error": {"code": code}, "verified_export": body}, None


def _validate_symbol_day_output(symbol: Any, day: Any, output_name: Any, samples: Any) -> None:
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.^_-]{0,31}", symbol):
        raise ChartError("SYMBOL_INVALID")
    try:
        valid_date = (isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
                      and calendar_date.fromisoformat(day).isoformat() == day)
    except ValueError:
        valid_date = False
    if not valid_date:
        raise ChartError("DATE_INVALID")
    if (not isinstance(output_name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", output_name)
            or output_name.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)],
                                       *[f"LPT{i}" for i in range(10)]}):
        raise ChartError("OUTPUT_NAME_INVALID")
    if type(samples) is not int or not 0 <= samples <= 50:
        raise ChartError("SAMPLES_INVALID")


class ChartService:
    def __init__(self, roots: Roots, execute: Callable = owned_execute,
                 export_python: Path | None = None, warm: Callable | None = None) -> None:
        """``warm`` (``WarmRenderer``): built with the gateway and export runtime, it draws the trade charts."""
        self.roots, self.execute = roots, execute
        if export_python is None:
            export_python = Path(sys.executable)
            if os.name != "nt":
                export_python = export_python.resolve(strict=True)
        self.export_python = checked_executable(export_python)
        self.warm = warm(roots.gateway, self.export_python) if warm is not None else None
        self._lock = threading.Lock()

    def close(self) -> dict[str, Any] | None:
        """Stop the warm renderer this server started, verified; ``None`` without one."""
        return self.warm.close() if self.warm is not None else None

    def export(self, symbol: str, day: str, output_name: str, samples: int = 0,
               cancel: threading.Event | None = None, as_of_m: int | None = None,
               annotations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": {"code": "EXPORT_BUSY"}}
        try:
            _validate_symbol_day_output(symbol, day, output_name, samples)
            checked_as_of, checked_notes = _validate_options(as_of_m, annotations)
            output = self.roots.output / output_name
            if os.path.lexists(output):
                raise ChartError("OUTPUT_ALREADY_EXISTS")
            cancel = cancel or threading.Event()
            if cancel.is_set():
                raise ChartError("CANCELLED")
            args = [str(self.export_python), "-B", str(self.roots.resolver / "tools/nova_historical_charts.py"),
                    "export", "--symbol", symbol, "--date", day, "--output", str(output),
                    "--samples", str(samples)]
            if checked_as_of is not None:
                args.extend(["--as-of-m", str(checked_as_of)])
            if checked_notes is not None:
                args.extend(["--annotations-json", json.dumps(checked_notes, separators=(",", ":"))])
            if self.roots.fallback_massive is not None:
                args.extend(["--fallback-massive-root", str(self.roots.fallback_massive)])
            args.extend(["--massive-root", str(self.roots.massive),
                         "--gateway-root", str(self.roots.gateway)])
            result = self.execute(args, self.roots.resolver, self.roots.gateway,
                                  cancel, REQUEST_TIMEOUT_SECONDS)
            if not result.trees_stopped or result.active_processes != 0:
                raise ChartError("OWNED_CLEANUP_UNVERIFIED")
            if result.returncode != 0:
                raise ChartError("EXPORT_FAILED")
            if cancel.is_set():
                raise ChartError("CANCELLED")
            return verify_export(output, symbol, day, samples)
        except ChartError as error:
            return {"ok": False, "error": {"code": str(error)}}
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            return {"ok": False, "error": {"code": "EXPORT_UNVERIFIED"}}
        finally:
            self._lock.release()

    def export_gallery(self, entries: list[dict[str, Any]], output_name: str,
                       family: str = "historical-chart", samples: int = 0,
                       cancel: threading.Event | None = None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": {"code": "EXPORT_BUSY"}}
        try:
            if not isinstance(entries, list) or not 1 <= len(entries) <= 9:
                raise ChartError("ENTRIES_INVALID")
            if not (isinstance(family, str) and 1 <= len(family) <= 80 and family == family.strip()
                    and all(32 <= ord(c) != 127 for c in family)):
                raise ChartError("FAMILY_INVALID")
            cleaned_entries: list[dict[str, Any]] = []
            seen: set[tuple[str, str, int]] = set()
            for item in entries:
                if not isinstance(item, dict):
                    raise ChartError("ENTRIES_INVALID")
                sym, d = item.get("symbol"), item.get("date")
                _validate_symbol_day_output(sym, d, output_name, samples)
                as_of, notes = _validate_options(item.get("as_of_m"), item.get("annotations"))
                ident = (d, sym, -1 if as_of is None else as_of)
                if ident in seen:
                    raise ChartError("DUPLICATE_ENTRY")
                seen.add(ident)
                entry_dict: dict[str, Any] = {"symbol": sym, "date": d}
                if as_of is not None:
                    entry_dict["as_of_m"] = as_of
                if notes is not None:
                    entry_dict["annotations"] = notes
                cleaned_entries.append(entry_dict)
            output = self.roots.output / output_name
            if os.path.lexists(output):
                raise ChartError("OUTPUT_ALREADY_EXISTS")
            cancel = cancel or threading.Event()
            if cancel.is_set():
                raise ChartError("CANCELLED")
            args = [str(self.export_python), "-B", str(self.roots.resolver / "tools/nova_historical_charts.py"),
                    "export", "--entries-json", json.dumps(cleaned_entries, separators=(",", ":")),
                    "--family", family, "--output", str(output), "--samples", str(samples)]
            if self.roots.fallback_massive is not None:
                args.extend(["--fallback-massive-root", str(self.roots.fallback_massive)])
            args.extend(["--massive-root", str(self.roots.massive),
                         "--gateway-root", str(self.roots.gateway)])
            result = self.execute(args, self.roots.resolver, self.roots.gateway,
                                  cancel, REQUEST_TIMEOUT_SECONDS)
            if not result.trees_stopped or result.active_processes != 0:
                raise ChartError("OWNED_CLEANUP_UNVERIFIED")
            if result.returncode != 0:
                raise ChartError("EXPORT_FAILED")
            if cancel.is_set():
                raise ChartError("CANCELLED")
            return verify_export(output, None, None, samples, expected_count=len(cleaned_entries))
        except ChartError as error:
            return {"ok": False, "error": {"code": str(error)}}
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            return {"ok": False, "error": {"code": "EXPORT_UNVERIFIED"}}
        finally:
            self._lock.release()

    def export_trades(self, trades: list[dict[str, Any]], output_name: str, bar_seconds: int = 10,
                      before_s: int = 300, after_s: int = 120, family: str | None = None, samples: int = 0,
                      cancel: threading.Event | None = None) -> dict[str, Any]:
        """Trade list in, marked sub-minute PNGs out; the CLI validates each trade, this boundary bounds the call."""
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": {"code": "EXPORT_BUSY"}}
        try:
            if (not isinstance(trades, list) or not 1 <= len(trades) <= MAX_TRADES
                    or not all(isinstance(t, dict) for t in trades)
                    or len(json.dumps(trades, allow_nan=False)) > MAX_TRADES_JSON_BYTES):
                raise ChartError("TRADES_INVALID")
            if type(bar_seconds) is not int or bar_seconds not in TRADE_BAR_SECONDS:
                raise ChartError("BAR_SECONDS_INVALID")
            if any(type(s) is not int or not 0 <= s <= 14400 for s in (before_s, after_s)):
                raise ChartError("WINDOW_INVALID")
            if family is not None and not (isinstance(family, str) and 1 <= len(family) <= 80
                                           and family == family.strip() and all(32 <= ord(c) != 127 for c in family)):
                raise ChartError("FAMILY_INVALID")
            _validate_symbol_day_output("TRADES", "2000-01-01", output_name, samples)
            script = self.roots.resolver / "tools/nova_trade_charts.py"
            if not script.is_file() or not script.resolve().is_relative_to(self.roots.resolver):
                raise ChartError("TRUSTED_ENTRYPOINT_MISSING")
            massive = self.roots.fallback_massive or self.roots.massive
            if not (massive / "trades_v1").is_dir():
                raise ChartError("TRADES_ROOT_MISSING")
            output = self.roots.output / output_name
            if os.path.lexists(output):
                raise ChartError("OUTPUT_ALREADY_EXISTS")
            cancel = cancel or threading.Event()
            args = [str(self.export_python), "-B", str(script), "export",
                    "--trades-json", json.dumps(trades, separators=(",", ":")), "--output", str(output),
                    "--bar-seconds", str(bar_seconds), "--before", str(before_s), "--after", str(after_s),
                    "--samples", str(samples), "--massive-root", str(massive),
                    "--gateway-root", str(self.roots.gateway)]
            if family is not None:
                args.extend(["--family", family])
            if cancel.is_set():
                raise ChartError("CANCELLED")
            warm_pid = warm_error = None
            if self.warm is not None:
                try:
                    warm_pid = self.warm.ensure()
                    args.extend(["--warm", "--idle-seconds", str(self.warm.idle_seconds)])
                except (WarmRendererUnavailable, OSError, ValueError):
                    warm_error = "WARM_RENDERER_UNAVAILABLE"  # Drawn one-shot instead; the answer says so.
            result = self.execute(args, self.roots.resolver, self.roots.gateway, cancel, REQUEST_TIMEOUT_SECONDS)
            if not result.trees_stopped or result.active_processes != 0:
                raise ChartError("OWNED_CLEANUP_UNVERIFIED")
            if result.returncode != 0:
                raise ChartError("EXPORT_FAILED")
            if cancel.is_set():
                raise ChartError("CANCELLED")
            selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
            body = verify_export(output, None, None, samples, expected_count=len(selection["selected"]),
                                 warm_pid=warm_pid)
            if warm_pid is None:
                body.update(renderer="one_shot", **({"warm_error": warm_error} if warm_error else {}))
            return body
        except ChartError as error:
            return {"ok": False, "error": {"code": str(error)}}
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            return {"ok": False, "error": {"code": "EXPORT_UNVERIFIED"}}
        finally:
            self._lock.release()


def create_server(service: ChartService):
    """The SDK implements MCP. Import lazily so stdlib fixture tests need no SDK."""
    try:
        if not sdk_version_ok(importlib.metadata.version("mcp")):
            raise ChartError("MCP_SDK_VERSION_REQUIRED")
        from mcp.server.fastmcp import FastMCP
        from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
        from pydantic import Field
    except (ImportError, importlib.metadata.PackageNotFoundError) as error:
        raise ChartError("MCP_SDK_NOT_INSTALLED") from error
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="nova-mcp-settings-") as empty:
        try:
            os.chdir(empty)
            server = FastMCP("nova-charts", log_level="WARNING")
        finally:
            os.chdir(previous)

    async def _run_export(call: Callable[[threading.Event], dict[str, Any]]):
        cancel = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(call, cancel))
        try:
            body = await asyncio.shield(task)
        except asyncio.CancelledError:
            cancel.set()
            await asyncio.shield(task)
            raise
        data = None
        if body.get("ok") is True:
            body, data = verified_inline_image(body, service.roots.output)
        content = [TextContent(type="text", text=json.dumps(body, allow_nan=False))]
        if data is not None:
            content.append(ImageContent(type="image", mimeType="image/png",
                                        data=base64.b64encode(data).decode("ascii")))
        return CallToolResult(content=content, structuredContent=body, isError=body.get("ok") is not True)

    async def historical_chart(symbol: str, date: str, output_name: str, samples: int = 0,
                               as_of_m: int | None = None,
                               annotations: list[dict[str, Any]] | None = None):
        """Export one local historical symbol/day with Nova; output_name must be new."""
        extra = {}
        if as_of_m is not None:
            extra["as_of_m"] = as_of_m
        if annotations is not None:
            extra["annotations"] = annotations
        return await _run_export(lambda cancel: service.export(
            symbol, date, output_name, samples, cancel, **extra))

    async def historical_chart_gallery(entries: list[dict[str, Any]], output_name: str,
                                       family: str = "historical-chart", samples: int = 0):
        """Export 1..9 local historical symbol/day entries as a 3x3 overview and per-entry 1m/5m charts."""
        return await _run_export(lambda cancel: service.export_gallery(
            entries, output_name, family, samples, cancel))

    async def trade_charts(trades: list[dict[str, Any]], output_name: str, bar_seconds: int = 10,
                           before_s: int = 300, after_s: int = 120, family: str | None = None, samples: int = 0):
        """Draw 1..9 stock-days of trades on 10-second (or 1/5/15/30 s) bars with buy/sell arrows, one PNG each.

        trades: [{symbol, date YYYY-MM-DD, entry_time "HH:MM:SS" ET, entry_price, exit_time, exit_price}] or
        exits [{time, price}] for partial exits; optional stop, pivot, label. Trades on one stock-day share a chart;
        the window is before_s before the first entry to after_s after the last exit. output_name must be new.
        Drawn by a warm renderer this server keeps running (it stops after 10 idle minutes and when the server ends).
        """
        return await _run_export(lambda cancel: service.export_trades(
            trades, output_name, bar_seconds, before_s, after_s, family, samples, cancel))

    for fn in (historical_chart, historical_chart_gallery, trade_charts):
        fn.__annotations__["samples"] = Annotated[int, Field(strict=True, ge=0, le=50)]
        fn.__annotations__["return"] = Annotated[CallToolResult, dict[str, Any]]
    annotations_hint = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
    server.tool(name="nova_historical_chart", annotations=annotations_hint)(historical_chart)
    server.tool(name="nova_historical_chart_gallery", annotations=annotations_hint)(historical_chart_gallery)
    server.tool(name="nova_trade_charts", annotations=annotations_hint)(trade_charts)
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("resolver", "gateway", "massive", "output"):
        parser.add_argument(f"--{name}-root", type=Path, required=True)
    parser.add_argument("--fallback-massive-root", type=Path, default=None)
    parser.add_argument("--export-python", type=Path, default=None,
                        help="Trusted existing resolver/export runtime; defaults to this SDK runtime")
    args = parser.parse_args()
    try:
        extra = (args.fallback_massive_root,) if args.fallback_massive_root is not None else ()
        roots = Roots.checked(args.resolver_root, args.gateway_root, args.massive_root, args.output_root, *extra)
        service = ChartService(roots, export_python=args.export_python, warm=WarmRenderer)
        try:
            create_server(service).run(transport="stdio")
        finally:
            print(json.dumps({"warm_renderer_shutdown": service.close()}), file=sys.stderr)
        return 0
    except ChartError as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError):
        print("MCP_STARTUP_INVALID", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

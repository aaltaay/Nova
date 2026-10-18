"""Optional official-SDK stdio access to bounded, stateless historical chart export.

The trusted launcher supplies roots; callers supply only symbol/day/output name.
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


SDK_VERSION = "1.26.0"
REQUEST_TIMEOUT_SECONDS = 240
MAX_RECEIPT_BYTES = 262_144
MAX_IMAGE_BYTES = 20_000_000
MAX_TOTAL_IMAGE_BYTES = 80_000_000
MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ChartError(Exception):
    """Only these fixed error codes may cross the MCP boundary."""


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

    @classmethod
    def checked(cls, resolver: Path, gateway: Path, massive: Path, output: Path) -> Roots:
        roots = cls(*(local_directory(p) for p in (resolver, gateway, massive, output)))
        for source in (roots.resolver, roots.gateway, roots.massive):
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
    # Windows Store Python's documented App Execution Alias is executable but
    # realpath(strict=True) raises WinError1920. Only this trusted launch token
    # gets that exception; data/output paths still reject every reparse point.
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


def verify_export(output: Path, symbol: str, day: str, samples: int) -> dict[str, Any]:
    if output.resolve(strict=True) != output:
        raise ChartError("OUTPUT_DIRECTORY_CHANGED")
    receipt_path = output / "historical_export.json"
    receipt = read_receipt(receipt_path, output)
    bundle = receipt.get("bundle", {})
    native = receipt.get("native_export", {})
    if (receipt.get("ok") is not True or receipt.get("schema_version") != 1
            or receipt.get("kind") != "historical_ohlcv"
            or bundle.get("symbol") != symbol or bundle.get("date") != day):
        raise ChartError("RECEIPT_IDENTITY_MISMATCH")
    if native != read_receipt(output / "images/EXPORT_RECEIPT.json", output):
        raise ChartError("NATIVE_RECEIPT_MISMATCH")
    if (native.get("ok") is not True or native.get("owned_trees_stopped") is not True
            or native.get("owned_children_stopped") is not True
            or type(native.get("active_owned_processes")) is not int
            or native["active_owned_processes"] != 0 or native.get("cleanup_errors") != []
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
    if (not isinstance(paths, list) or len(paths) != 3 or native.get("selected_count") != 1
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
    return {"ok": True, "schema_version": 1, "symbol": symbol, "date": day,
            "samples": samples, "images": images, "selection_sha256": selection_sha,
            "receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path)},
            "owned_tree_verified": True, "active_owned_processes": 0}


def verified_inline_image(body: dict[str, Any], approved_output: Path) -> tuple[dict[str, Any], bytes | None]:
    """Recheck only the unique verified detail image; never accept caller paths."""
    try:
        candidates = [item for item in body["images"]
                      if Path(item["path"]).name.endswith("_1m_5m.png")]
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


class ChartService:
    def __init__(self, roots: Roots, execute: Callable = owned_execute,
                 export_python: Path | None = None) -> None:
        self.roots, self.execute = roots, execute
        if export_python is None:
            export_python = Path(sys.executable)
            if os.name != "nt":
                export_python = export_python.resolve(strict=True)
        self.export_python = checked_executable(export_python)
        self._lock = threading.Lock()

    def export(self, symbol: str, day: str, output_name: str, samples: int = 0,
               cancel: threading.Event | None = None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": {"code": "EXPORT_BUSY"}}
        try:
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
            output = self.roots.output / output_name
            if os.path.lexists(output):
                raise ChartError("OUTPUT_ALREADY_EXISTS")
            cancel = cancel or threading.Event()
            if cancel.is_set():
                raise ChartError("CANCELLED")
            args = [str(self.export_python), "-B", str(self.roots.resolver / "tools/nova_historical_charts.py"),
                    "export", "--symbol", symbol, "--date", day, "--output", str(output),
                    "--samples", str(samples), "--massive-root", str(self.roots.massive),
                    "--gateway-root", str(self.roots.gateway)]
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


def create_server(service: ChartService):
    """The SDK implements MCP. Import lazily so stdlib fixture tests need no SDK."""
    try:
        if importlib.metadata.version("mcp") != SDK_VERSION:
            raise ChartError("MCP_SDK_VERSION_REQUIRED")
        from mcp.server.fastmcp import FastMCP
        from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
        from pydantic import Field
    except (ImportError, importlib.metadata.PackageNotFoundError) as error:
        raise ChartError("MCP_SDK_NOT_INSTALLED") from error
    # Pinned FastMCP Settings defaults to reading .env in cwd. Construct at
    # startup, before any request threads exist, in a private empty directory.
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="nova-mcp-settings-") as empty:
        try:
            os.chdir(empty)
            server = FastMCP("nova-charts", log_level="WARNING")
        finally:
            os.chdir(previous)

    async def historical_chart(symbol: str, date: str, output_name: str,
                               samples: int = 0):
        """Export one local historical symbol/day with Nova; output_name must be new.

        Writes verified PNGs under the host-approved output root. No desk/Sim,
        broker, downloads or live history. Inspect ok/error before using artifacts.
        """
        cancel = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(
            service.export, symbol, date, output_name, samples, cancel))
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

    # Keep booleans/floats from being coerced into an integer before our boundary.
    historical_chart.__annotations__["samples"] = Annotated[int, Field(strict=True, ge=0, le=50)]
    historical_chart.__annotations__["return"] = Annotated[CallToolResult, dict[str, Any]]
    server.tool(name="nova_historical_chart", annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False,
        openWorldHint=False))(historical_chart)
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("resolver", "gateway", "massive", "output"):
        parser.add_argument(f"--{name}-root", type=Path, required=True)
    parser.add_argument("--export-python", type=Path, default=None,
                        help="Trusted existing resolver/export runtime; defaults to this SDK runtime")
    args = parser.parse_args()
    try:
        roots = Roots.checked(args.resolver_root, args.gateway_root, args.massive_root, args.output_root)
        create_server(ChartService(roots, export_python=args.export_python)).run(transport="stdio")
        return 0
    except ChartError as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError):
        print("MCP_STARTUP_INVALID", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

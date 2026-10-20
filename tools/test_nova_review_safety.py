"""Review engine safety: real bars, shot token, asset jail, bind probe, rotation."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_data_mcp as data  # noqa: E402
import nova_mcp  # noqa: E402
import nova_review_causal as causal  # noqa: E402
import nova_review_engine as engine  # noqa: E402
import nova_review_http as review_http  # noqa: E402
import nova_review_warm as review_warm  # noqa: E402

DAY = "2026-09-18"
ET = causal.ET
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


def _minute():
    from datetime import datetime
    return {
        "time_et": datetime(2026, 9, 18, 9, 30, tzinfo=ET),
        "open": 4.5, "high": 5.0, "low": 4.2, "close": 4.8, "volume": 100,
    }


def _bars(_symbol, _day, _tf):
    return [_minute()]


def _daily(*_args):
    return []


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _serve(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("NOVA_REVIEW_LEASE", str(tmp_path / "lease.json"))
    monkeypatch.setenv("NOVA_REVIEW_LEASE_LOCK", str(tmp_path / "lease.lock"))
    monkeypatch.setenv("NOVA_REVIEW_SHOT_DIR", str(tmp_path / "shots"))
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>review</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("safe-asset", encoding="utf-8")
    monkeypatch.setenv("NOVA_REVIEW_DIST", str(dist))
    engine.STATE.token = ""
    engine.STATE.shots = None
    engine.STATE._counted = False
    httpd = engine.serve_engine(0, bars_reader=_bars, daily_reader=_daily)
    assert httpd is not None
    threading.Thread(target=httpd.serve_forever, name="nova-review-test", daemon=True).start()
    review_http._write_lease(int(httpd.server_address[1]), engine.STATE.token)
    return httpd


def _raw(port: int, path: str) -> bytes:
    sock = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode()
        )
        chunks = []
        while True:
            block = sock.recv(65536)
            if not block:
                break
            chunks.append(block)
    finally:
        sock.close()
    return b"".join(chunks)


def _post(port: int, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/review/shot",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_the_engine_serves_review_bars(tmp_path, monkeypatch):
    httpd = _serve(monkeypatch, tmp_path)
    port = int(httpd.server_address[1])
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/review?symbol=IMCC&date={DAY}&tf=1m&as_of=10:00",
            timeout=5,
        ) as response:
            body = json.loads(response.read().decode())
            status = response.status
        assert status == 200
        assert body["ok"] is True
        assert body["timeframes"]["1m"]["bars"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_nova_chart_through_the_real_engine_returns_an_image(tmp_path, monkeypatch):
    httpd = _serve(monkeypatch, tmp_path)
    port = int(httpd.server_address[1])
    monkeypatch.delenv("NOVA_REVIEW_BASE", raising=False)

    def shoot(url: str, dest: Path) -> dict:
        assert url.startswith(f"http://127.0.0.1:{port}/review")
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/review?symbol=IMCC&date={DAY}&tf=1m&as_of=16:00",
            timeout=5,
        ) as response:
            payload = json.loads(response.read().decode())
        assert payload["ok"] is True and payload["timeframes"]["1m"]["bars"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(PNG)
        return {"ok": True, "sha256": hashlib.sha256(PNG).hexdigest(), "bytes": len(PNG), "png": PNG}

    engine.STATE.shots = review_warm.ReviewShots(shoot=shoot)
    try:
        server = nova_mcp.create_server(
            data.DataService(tmp_path / "out"),
            review_port=port,
            http=True,
            warm=True,
            shots=None,
        )
        result = asyncio.run(server.call_tool("nova_chart", {"symbols": ["IMCC"], "date": DAY}))
        assert result.isError is not True
        assert result.structuredContent["ok"] is True
        assert sum(1 for block in result.content if block.type == "image") == 1
        assert result.content[1].data == base64.b64encode(PNG).decode("ascii")
    finally:
        engine.STATE.shots = None
        httpd.shutdown()
        httpd.server_close()


def test_shot_rejects_a_browser_post_and_ignores_client_paths(tmp_path, monkeypatch):
    httpd = _serve(monkeypatch, tmp_path)
    port = int(httpd.server_address[1])
    token = engine.STATE.token
    good = {"id": "abc", "symbol": "IMCC", "date": DAY, "as_of": "10:00"}
    evil = tmp_path / "evil.png"
    try:
        status, _body = _post(
            port,
            json.dumps(good).encode(),
            {"Content-Type": "text/plain", "X-Nova-Review-Token": token},
        )
        assert status == 415
        status, _body = _post(port, json.dumps(good).encode(), {"Content-Type": "application/json"})
        assert status == 401
        status, _body = _post(
            port,
            json.dumps(good).encode(),
            {
                "Content-Type": "application/json",
                "X-Nova-Review-Token": token,
                "Origin": "http://evil.test",
            },
        )
        assert status == 403
        status, _body = _post(
            port,
            json.dumps({**good, "dest": str(evil)}).encode(),
            {"Content-Type": "application/json", "X-Nova-Review-Token": token},
        )
        assert status == 400
        assert not evil.exists()
        status, _body = _post(
            port,
            json.dumps({**good, "url": "http://evil.test/steal"}).encode(),
            {"Content-Type": "application/json", "X-Nova-Review-Token": token},
        )
        assert status == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_asset_paths_stay_inside_dist(tmp_path, monkeypatch):
    httpd = _serve(monkeypatch, tmp_path)
    port = int(httpd.server_address[1])
    secret = (Path(__file__).resolve().parent / "nova_mcp.py").read_bytes()
    try:
        escaped = _raw(port, "/assets/../../../tools/nova_mcp.py")
        encoded = _raw(port, "/assets/%2e%2e/%2e%2e/%2e%2e/tools/nova_mcp.py")
        kept = _raw(port, "/assets/app.js")
        assert b" 404 " in escaped
        assert secret[:40] not in escaped
        assert b" 404 " in encoded
        assert secret[:40] not in encoded
        assert b" 200 " in kept and b"safe-asset" in kept
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_healthy_review_port_is_not_bound_again(monkeypatch):
    port = _free_port()
    monkeypatch.setattr(review_http, "health_ok", lambda asked: asked == port)
    httpd = engine.serve_engine(port, bars_reader=_bars, daily_reader=_daily)
    try:
        assert httpd is None
        sock = socket.socket()
        sock.bind(("127.0.0.1", port))
        sock.close()
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()


def test_rotate_survives_a_png_deleted_during_the_scan(tmp_path, monkeypatch):
    for index in range(30):
        (tmp_path / f"review-x-{index}.png").write_bytes(b"x" * 20)
    real = Path.stat
    seen = {"n": 0}

    def flaky(self, *args, **kwargs):
        if self.parent == tmp_path and self.suffix == ".png":
            seen["n"] += 1
            if seen["n"] == 1:
                self.unlink()
                raise FileNotFoundError(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky)
    review_warm.rotate_shots(tmp_path)


def test_rotate_keeps_a_file_another_request_will_return(tmp_path):
    oldest = tmp_path / "review-x-0.png"
    for index in range(30):
        path = tmp_path / f"review-x-{index}.png"
        path.write_bytes(b"x" * 10)
        os.utime(path, (index + 1, index + 1))
    review_warm.rotate_shots(tmp_path, protect={oldest.resolve()})
    assert oldest.exists()


def test_four_concurrent_charts_all_return_images(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_REVIEW_BASE", raising=False)
    folder = tmp_path / "review-shots"
    folder.mkdir()
    for index in range(30):
        path = folder / f"review-old-{index}.png"
        path.write_bytes(b"x" * 50)
        os.utime(path, (index + 1, index + 1))

    def shoot(_url: str, dest: Path) -> dict:
        import time
        time.sleep(0.05)
        dest.write_bytes(PNG)
        return {"ok": True, "sha256": hashlib.sha256(PNG).hexdigest(), "bytes": len(PNG), "png": PNG}

    shots = review_warm.ReviewShots(shoot=shoot)
    server = nova_mcp.create_server(
        data.DataService(tmp_path), http=False, warm=True, shots=shots,
    )
    found: list = []
    errors: list = []

    def call() -> None:
        try:
            found.append(asyncio.run(server.call_tool(
                "nova_chart", {"symbols": ["IMCC"], "date": DAY},
            )))
        except Exception as exc:  # noqa: BLE001 - the test records a dropped chart
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    assert len(found) == 4
    for result in found:
        assert result.structuredContent["ok"] is True
        assert sum(1 for block in result.content if block.type == "image") == 1


def test_links_default_to_the_engine_and_the_env_still_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_REVIEW_BASE", raising=False)
    assert nova_mcp.default_review_base() == ""
    httpd = _serve(monkeypatch, tmp_path)
    port = int(httpd.server_address[1])
    try:
        server = nova_mcp.create_server(
            data.DataService(tmp_path / "out"),
            review_port=port,
            http=True,
            warm=False,
        )
        result = asyncio.run(server.call_tool("nova_chart", {"symbols": ["IMCC"], "date": DAY}))
        link = result.structuredContent["links"][0]["url"]
        assert f"127.0.0.1:{port}" in link
        assert ":5173" not in link
        monkeypatch.setenv("NOVA_REVIEW_BASE", "http://127.0.0.1:4173")
        override = nova_mcp.create_server(
            data.DataService(tmp_path / "out2"),
            review_base="http://127.0.0.1:4173",
            review_port=port,
            http=True,
            warm=False,
        )
        second = asyncio.run(override.call_tool("nova_chart", {"symbols": ["IMCC"], "date": DAY}))
        assert "127.0.0.1:4173" in second.structuredContent["links"][0]["url"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_full_width_clock_is_a_bad_request_not_a_crash(tmp_path):
    server = nova_mcp.create_server(data.DataService(tmp_path), http=False, warm=False)
    result = asyncio.run(server.call_tool(
        "nova_chart", {"symbols": ["IMCC"], "date": DAY, "as_of": "10：00"},
    ))
    assert result.isError is not True
    assert result.structuredContent["ok"] is False
    assert result.structuredContent["error"]["code"] == "BAD_REQUEST"
    assert result.content[0].text == result.structuredContent["chat_message"]
    assert "：" not in result.content[0].text


def _resolve(src: Path, spec: str) -> Path | None:
    base = (src.parent / spec).resolve()
    for cand in (base, base.with_suffix(".ts"), base.with_suffix(".tsx"), base / "index.ts", base / "index.tsx"):
        if cand.is_file():
            return cand
    return None


def _value_imports(path: Path) -> list[tuple[str, list[str] | None]]:
    import re
    text = re.sub(r"""import\s*\(\s*['\"][^'\"]+['\"]\s*\)""", "''", path.read_text(encoding="utf-8"))
    found = []
    for match in re.finditer(
        r"""import\s+(type\s+)?(?:([\w*{}\s,]+)\s+from\s+)?['\"](\.[^'\"]+)['\"]""",
        text,
    ):
        if match.group(1):
            continue
        clause, spec = match.group(2), match.group(3)
        if clause is None:
            found.append((spec, None))
            continue
        raw = clause.strip()
        if raw.startswith("{"):
            names = []
            for part in raw.strip("{} ").split(","):
                part = " ".join(part.split())
                if not part or part.startswith("type "):
                    continue
                names.append(part.split(" as ")[0].strip())
            if names:
                found.append((spec, names))
        else:
            found.append((spec, ["*"]))
    return found


def _reexports(path: Path) -> list[tuple[str, list[str]]]:
    import re
    rows = []
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(
        r"""export\s+(type\s+)?\{([^}]+)\}\s+from\s+['\"](\.[^'\"]+)['\"]""",
        text,
    ):
        if match.group(1):
            continue
        names = []
        for part in match.group(2).split(","):
            part = " ".join(part.split())
            if not part or part.startswith("type "):
                continue
            names.append(part.split(" as ")[-1].strip())
        rows.append((match.group(3), names))
    return rows


def _closure(start: Path) -> set[Path]:
    seen: set[Path] = set()
    stack = [start]
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        for spec, names in _value_imports(path):
            dest = _resolve(path, spec)
            if dest is None:
                continue
            stack.append(dest)
            if names is None:
                continue
            for spec2, exported in _reexports(dest):
                if names == ["*"] or any(name in exported for name in names):
                    nxt = _resolve(dest, spec2)
                    if nxt is not None:
                        stack.append(nxt)
    return seen


def test_review_does_not_load_bots_or_the_fixture_module():
    review = _closure(SRC / "review" / "mountReview.tsx")
    names = {path.name for path in review}
    assert "useBotAllowlist.ts" not in names
    assert "bots_page.ts" not in names
    assert "constants.ts" not in {path.name for path in review if path.parent == SRC}
    assert "reviewFixture.ts" not in names
    entry = _closure(SRC / "main.tsx")
    entry_names = {path.name for path in entry}
    assert "bots_page.ts" not in entry_names
    assert "useBotAllowlist.ts" not in entry_names
    assert "constants.ts" not in {path.name for path in entry if path.parent == SRC}

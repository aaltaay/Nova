"""tools/serve_phone_page.py -- the built phone page, served to the private tunnel (ADR 070).

Found 2026-11-11 by opening the phone page through the tunnel: behind ``python -m http.server`` a first
load's burst of files came back 502 for a share of them (69 of 240 in three bursts), and the page did
not start. These hold the three things the replacement is for: a burst is answered whole, a phone gets
the new build on a reload, and it serves one folder on this PC and nothing else.
"""
from __future__ import annotations

import http.client
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import serve_phone_page  # noqa: E402


@pytest.fixture
def page(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "phone.html").write_text("<!doctype html><title>Nova</title>", encoding="utf-8")
    (tmp_path / "phone" ).mkdir()
    (tmp_path / "phone" / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    for i in range(80):
        (tmp_path / "assets" / f"chunk-{i:02d}.js").write_text(f"export const n = {i};", encoding="utf-8")
    (tmp_path.parent / "outside.txt").write_text("not the page", encoding="utf-8")
    server = serve_phone_page.make_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _get(port: int, path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path)
        res = conn.getresponse()
        return res.status, {k.lower(): v for k, v in res.getheaders()}, res.read()
    finally:
        conn.close()


def test_it_listens_on_this_pc_only(page):
    assert serve_phone_page.LOOPBACK == "127.0.0.1"
    server = serve_phone_page.make_server(Path("."), 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_a_first_loads_burst_of_files_is_answered_whole(page):
    paths = [f"/assets/chunk-{i:02d}.js" for i in range(80)] * 3
    with ThreadPoolExecutor(max_workers=80) as pool:
        statuses = list(pool.map(lambda p: _get(page, p)[0], paths))
    assert statuses.count(200) == len(paths)


def test_it_names_each_files_type_itself_never_from_the_registry(page, monkeypatch):
    # The operating system's table is slow on its first read and can call a script plain text.
    import mimetypes

    def never(*_a, **_k):
        raise AssertionError("the registry was asked for a file type")

    monkeypatch.setattr(mimetypes, "guess_type", never)
    assert _get(page, "/assets/chunk-00.js")[1]["content-type"] == "text/javascript; charset=utf-8"
    assert _get(page, "/phone.html")[1]["content-type"] == "text/html; charset=utf-8"
    assert _get(page, "/phone/manifest.webmanifest")[1]["content-type"] == "application/manifest+json"
    assert serve_phone_page.CONTENT_TYPES[".woff2"] == "font/woff2"
    assert serve_phone_page.CONTENT_TYPES[".css"].startswith("text/css")


def test_a_kind_of_file_it_does_not_know_is_bytes_not_a_guess(tmp_path):
    (tmp_path / "phone.html").write_text("x", encoding="utf-8")
    (tmp_path / "thing.xyz").write_text("x", encoding="utf-8")
    server = serve_phone_page.make_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _get(server.server_address[1], "/thing.xyz")[1]["content-type"] == "application/octet-stream"
    finally:
        server.shutdown()
        server.server_close()


def test_one_connection_carries_many_files(page):
    # HTTP/1.1 keep-alive: the tunnel's proxy reuses a connection instead of dialling for every file.
    conn = http.client.HTTPConnection("127.0.0.1", page, timeout=10)
    try:
        for i in range(5):
            conn.request("GET", f"/assets/chunk-{i:02d}.js")
            res = conn.getresponse()
            assert res.version == 11 and res.status == 200
            assert res.read() == f"export const n = {i};".encode()
    finally:
        conn.close()


def test_a_hashed_file_may_be_kept_and_a_page_is_asked_for_again(page):
    assert _get(page, "/assets/chunk-00.js")[1]["cache-control"] == serve_phone_page.CACHE_HASHED
    assert "immutable" in serve_phone_page.CACHE_HASHED
    # A reload after a new build must show it: the page and the manifest are never kept without asking.
    assert _get(page, "/phone.html")[1]["cache-control"] == "no-cache"
    assert _get(page, "/phone.html?v=2")[1]["cache-control"] == "no-cache"
    assert _get(page, "/phone/manifest.webmanifest")[1]["cache-control"] == "no-cache"
    assert serve_phone_page.cache_control("/assets/a.js?x=1") == serve_phone_page.CACHE_HASHED
    assert serve_phone_page.cache_control("/assetsx/a.js") == "no-cache"


def test_it_serves_the_one_folder_and_nothing_else(page):
    assert _get(page, "/phone.html")[0] == 200
    # No folder is listed, nothing above the folder is reachable, and a missing file is a 404.
    assert _get(page, "/assets/")[0] == 404
    assert _get(page, "/../outside.txt")[0] == 404
    assert _get(page, "/..%2foutside.txt")[0] == 404
    assert _get(page, "/assets/../../outside.txt")[0] == 404
    assert _get(page, "/nothing-here.js")[0] == 404


def test_it_takes_no_write(page):
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert _get(page, "/phone.html", method)[0] == 501


def test_it_will_not_start_on_a_folder_with_no_phone_page(tmp_path, capsys):
    assert serve_phone_page.main(["--directory", str(tmp_path), "--port", "0"]) == 2
    assert "npm run build" in capsys.readouterr().err

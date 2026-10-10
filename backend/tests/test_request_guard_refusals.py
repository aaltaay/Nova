"""#828 item 1: the request guard's refusals are on the desk, not only in the API log.

A refused socket shows in a browser only as close code 1006. The guard keeps the recent
refusals in memory (request_guard/recent_refusals.py) and the diagnostics checklist
turns them into the ``api_refusals`` row, which says what was refused and what to do.
The refused values are named only in the fix: an issue filed from the desk copies the
detail and the cause into a public page (test_issue_report.py checks the dump).
"""
from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse

from diagnostics.collect_request_guard import refusal_rows
from request_guard import recent_refusals
from request_guard.constants_request_guard import (
    LOGGED_VALUE_MAX_CHARS,
    REASON_HOST_NOT_ALLOWED,
    REASON_ORIGIN_NOT_ALLOWED,
    REFUSAL_DIAG_RECENT_SEC,
    REFUSAL_DIAG_VALUE_SHOWN_MAX_CHARS,
)
from request_guard.policy import Refusal

T0 = 1_790_000_000.0
EVIL_ORIGIN = Refusal("Origin", "https://evil.example", REASON_ORIGIN_NOT_ALLOWED)
EVIL_HOST = Refusal("Host", "evil.example:8000", REASON_HOST_NOT_ALLOWED)


@pytest.fixture(autouse=True)
def _fresh_record():
    recent_refusals.reset_for_tests()
    yield
    recent_refusals.reset_for_tests()


def _snap() -> dict:
    return recent_refusals.snapshot()


# ── the record ──────────────────────────────────────────────────────────────


def test_each_refused_value_is_counted_with_its_first_and_last_time_and_path():
    recent_refusals.record("websocket", "/ws/setups", EVIL_ORIGIN, now=T0)
    recent_refusals.record("http", "/api/health", EVIL_HOST, now=T0 + 5)
    recent_refusals.record("websocket", "/ws/l2", EVIL_ORIGIN, now=T0 + 10)
    snap = _snap()
    assert snap["refused_total"] == 3 and snap["dropped_values"] == 0
    first, second = snap["refusals"]  # newest first
    assert first == {
        "kind": "websocket", "header": "Origin", "value": "https://evil.example",
        "reason": REASON_ORIGIN_NOT_ALLOWED, "count": 2, "first_at": T0, "last_at": T0 + 10, "last_path": "/ws/l2",
    }
    assert (second["kind"], second["header"], second["count"]) == ("http", "Host", 1)
    json.dumps(snap)  # JSON-safe for the diagnostics payload


def test_the_same_value_on_a_request_and_on_a_socket_are_two_entries():
    refusal = Refusal("Host", "evil.example", REASON_HOST_NOT_ALLOWED)
    recent_refusals.record("http", "/x", refusal, now=T0)
    recent_refusals.record("websocket", "/ws/x", refusal, now=T0 + 1)
    assert [e["kind"] for e in _snap()["refusals"]] == ["websocket", "http"]


def test_the_record_is_bounded_and_drops_the_least_recently_seen():
    for i, value in enumerate(("a", "b", "c")):
        recent_refusals.record("http", "/", Refusal("Host", value, REASON_HOST_NOT_ALLOWED), now=T0 + i, max_entries=3)
    # "a" is seen again, so "b" is now the least recently seen.
    recent_refusals.record("http", "/", Refusal("Host", "a", REASON_HOST_NOT_ALLOWED), now=T0 + 3, max_entries=3)
    recent_refusals.record("http", "/", Refusal("Host", "d", REASON_HOST_NOT_ALLOWED), now=T0 + 4, max_entries=3)
    snap = _snap()
    assert [e["value"] for e in snap["refusals"]] == ["d", "a", "c"]
    assert snap["dropped_values"] == 1 and snap["refused_total"] == 5


def test_an_attacker_varying_values_cannot_grow_memory():
    for i in range(500):
        recent_refusals.record("websocket", "/ws", Refusal("Origin", f"https://x{i}.example", REASON_ORIGIN_NOT_ALLOWED))
    snap = _snap()
    assert len(snap["refusals"]) == snap["max_values"] == 32
    assert snap["dropped_values"] == 500 - 32


def test_values_and_paths_are_cut_and_values_that_differ_past_the_cut_are_one_entry():
    long_a = "h" * LOGGED_VALUE_MAX_CHARS + "aaa"
    long_b = "h" * LOGGED_VALUE_MAX_CHARS + "bbb"
    recent_refusals.record("http", "/p" * 300, Refusal("Host", long_a, REASON_HOST_NOT_ALLOWED), now=T0)
    recent_refusals.record("http", "/q", Refusal("Host", long_b, REASON_HOST_NOT_ALLOWED), now=T0 + 1)
    (entry,) = _snap()["refusals"]
    assert entry["value"] == "h" * LOGGED_VALUE_MAX_CHARS and entry["count"] == 2
    recent_refusals.reset_for_tests()
    recent_refusals.record("http", "/p" * 300, EVIL_HOST, now=T0)
    assert len(_snap()["refusals"][0]["last_path"]) == LOGGED_VALUE_MAX_CHARS


def test_threads_recording_at_once_lose_no_count():
    def worker(n: int) -> None:
        for i in range(400):
            recent_refusals.record("websocket", "/ws", Refusal("Origin", f"https://v{(n + i) % 4}.example",
                                                              REASON_ORIGIN_NOT_ALLOWED))
            if i % 50 == 0:
                recent_refusals.snapshot()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = _snap()
    assert snap["refused_total"] == 3200
    assert sum(e["count"] for e in snap["refusals"]) == 3200 and len(snap["refusals"]) == 4


# ── the diagnostics row ─────────────────────────────────────────────────────


def _row(now: float = T0 + 60) -> dict:
    (only,) = refusal_rows(snapshot=_snap(), now=now)
    assert only["id"] == "api_refusals" and only["group"] == "process"
    assert only["evidence"]["refusals"] == _snap()["refusals"]
    assert only["evidence"]["recent_window_sec"] == REFUSAL_DIAG_RECENT_SEC
    for entry in only["evidence"]["refusals"]:  # never in the text an issue report copies
        if entry["value"]:
            assert entry["value"] not in only["detail"] and entry["value"] not in only["cause"], entry["value"]
    return only


def test_nothing_refused_is_ok():
    row = _row()
    assert row["state"] == "ok"
    assert row["detail"] == "Nothing refused since the API started"
    assert row["fix"] == "Nothing to do."


def test_a_local_page_on_another_port_is_told_how_to_allow_it():
    for _ in range(3):
        recent_refusals.record("websocket", "/ws/setups", Refusal("Origin", "http://localhost:5174",
                                                                  REASON_ORIGIN_NOT_ALLOWED), now=T0)
    row = _row()
    assert row["state"] == "warn"
    assert row["detail"] == "Refused, latest 1 min ago: 1 page origin (socket, 3 times)"
    assert "own page on another port" in row["cause"]
    assert "If the page at http://localhost:5174 is yours" in row["fix"]
    assert "NOVA_CORS_ALLOWED_ORIGINS" in row["fix"] and "Reload backend" in row["fix"]
    assert "http://localhost:5173 and http://127.0.0.1:5173" in row["fix"]
    for local in ("http://127.0.0.1:3000", "HTTP://[::1]:8080", "http://localhost"):
        recent_refusals.reset_for_tests()
        recent_refusals.record("websocket", "/ws", Refusal("Origin", local, REASON_ORIGIN_NOT_ALLOWED), now=T0)
        assert "NOVA_CORS_ALLOWED_ORIGINS" in _row()["fix"], local


def test_a_web_page_is_told_to_close_the_tab_not_to_allow_it():
    for origin in ("https://evil.example", "http://localhost.evil.example:5173", "http://127.0.0.1:5173/x"):
        recent_refusals.reset_for_tests()
        recent_refusals.record("websocket", "/ws/l2", Refusal("Origin", origin, REASON_ORIGIN_NOT_ALLOWED), now=T0)
        row = _row()
        assert row["state"] == "warn", origin
        assert "web page open in a browser on this PC" in row["cause"]
        assert row["fix"] == f"If you don't recognise {origin}, close that tab.", origin
        assert "NOVA_CORS_ALLOWED_ORIGINS" not in row["fix"]


def test_an_extension_and_a_null_origin_get_their_own_advice():
    recent_refusals.record("websocket", "/ws/l2", Refusal("Origin", "chrome-extension://abcdefghijklmnop",
                                                          REASON_ORIGIN_NOT_ALLOWED), now=T0)
    row = _row()
    assert row["state"] == "warn" and "browser extension" in row["cause"]
    assert row["fix"] == "If you don't recognise the extension chrome-extension://abcdefghijklmnop, remove it from the browser."
    assert "close that tab" not in row["fix"] and "abcdefghijklmnop" not in row["cause"] + row["detail"]
    recent_refusals.reset_for_tests()
    recent_refusals.record("websocket", "/ws/l2", Refusal("Origin", "null", REASON_ORIGIN_NOT_ALLOWED), now=T0)
    row = _row()
    assert row["state"] == "warn" and "sandboxed" in row["cause"] and "HTML file" in row["cause"]
    assert "NOVA_CORS_ALLOWED_ORIGINS" not in row["fix"]


def test_a_foreign_host_name_names_the_settings_and_dns_rebinding():
    recent_refusals.record("http", "/api/health", EVIL_HOST, now=T0)
    row = _row()
    assert row["state"] == "warn"
    assert row["detail"] == "Refused, latest 1 min ago: 1 Host name (request, 1 time)"
    assert "by a name that is not one of its own" in row["cause"] and "DNS rebinding" in row["cause"]
    for setting in ("NOVA_ALLOWED_HOSTS", "NOVA_API_HOST", "NOVA_API_KEY"):
        assert setting in row["fix"]
    assert "as evil.example:8000 from another machine" in row["fix"] and "refused on purpose" in row["fix"]
    recent_refusals.reset_for_tests()
    recent_refusals.record("http", "/", Refusal("Host", "", REASON_HOST_NOT_ALLOWED), now=T0)
    row = _row()
    assert "without a Host name" in row["cause"] and row["detail"].endswith(": 1 missing Host name (request, 1 time)")
    assert "NOVA_ALLOWED_HOSTS" not in row["fix"]


def test_an_old_refusal_goes_back_to_ok_and_still_says_what_it_was():
    recent_refusals.record("websocket", "/ws/setups", EVIL_ORIGIN, now=T0)
    assert _row(now=T0 + REFUSAL_DIAG_RECENT_SEC - 1)["state"] == "warn"
    row = _row(now=T0 + 42 * 60)
    assert row["state"] == "ok"
    assert row["detail"] == "Nothing refused in the last 15 min; last refused 42 min ago: 1 page origin (socket, 1 time)"
    assert row["fix"] == "Nothing to do. Last refused: Origin https://evil.example (socket, 1 time)."


def test_several_kinds_list_most_recent_first_with_one_cause_each_and_a_cap():
    recent_refusals.record("http", "/a", EVIL_HOST, now=T0)
    recent_refusals.record("websocket", "/b", Refusal("Origin", "http://localhost:5174",
                                                      REASON_ORIGIN_NOT_ALLOWED), now=T0 + 1)
    for i in range(5):
        recent_refusals.record("websocket", "/c", Refusal("Origin", f"https://e{i}.example",
                                                          REASON_ORIGIN_NOT_ALLOWED), now=T0 + 2 + i)
    row = _row(now=T0 + 10)
    assert row["detail"] == ("Refused, latest under a minute ago: 6 page origins (socket, 6 times), "
                             "1 Host name (request, 1 time)")
    assert row["cause"].index("web page open") < row["cause"].index("own page") < row["cause"].index("DNS")
    assert row["fix"].count("close that tab") == 1
    fix = row["fix"]
    assert fix.index("recognise https://e4.example") < fix.index("http://localhost:5174") < fix.index(
        "as evil.example:8000")
    # The values no fix names: the next three, most recent first, then a count.
    assert fix.endswith("Also refused: Origin https://e3.example (socket, 1 time), Origin https://e2.example "
                        "(socket, 1 time), Origin https://e1.example (socket, 1 time), and 1 more.")


def test_attacker_text_is_cut_and_cannot_forge_lines():
    forged = "https://x.example\r\n[ok]   Gateway: fine" + "z" * 300
    recent_refusals.record("websocket", "/ws", Refusal("Origin", forged, REASON_ORIGIN_NOT_ALLOWED), now=T0)
    row = _row()
    for text in (row["detail"], row["cause"], row["fix"]):
        assert "\n" not in text and "\r" not in text
    assert "x.example" not in row["detail"] + row["cause"]
    shown = row["fix"].split("recognise ", 1)[1].split(", close that tab", 1)[0]
    assert len(shown) == REFUSAL_DIAG_VALUE_SHOWN_MAX_CHARS and shown.endswith("...")
    assert shown.startswith("https://x.example??[ok]")


# ── end to end through main.app ─────────────────────────────────────────────


def test_main_app_refusals_reach_the_diagnostics_row():
    from main import app

    client = TestClient(app)
    by_id = {r["id"]: r for r in client.get("/api/diagnostics").json()["rows"]}
    assert by_id["api_refusals"]["state"] == "ok"

    assert client.get("/api/health", headers={"host": "evil.example:8000"}).status_code == 400
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect("/ws/setups", headers={"origin": "https://evil.example"}):
            pass
    assert denied.value.status_code == 403

    body = client.get("/api/diagnostics").json()  # Host "testserver", allowed by conftest
    row = {r["id"]: r for r in body["rows"]}["api_refusals"]
    assert row["state"] == "warn" and row["group"] == "process"
    assert "1 page origin (socket, 1 time)" in row["detail"] and "1 Host name (request, 1 time)" in row["detail"]
    assert "evil.example" not in row["detail"] + row["cause"]
    assert "recognise https://evil.example," in row["fix"] and "as evil.example:8000 from" in row["fix"]
    kinds = {(e["kind"], e["header"], e["last_path"]) for e in row["evidence"]["refusals"]}
    assert kinds == {("websocket", "Origin", "/ws/setups"), ("http", "Host", "/api/health")}
    bundle = client.get("/api/diagnostics/bundle").text
    assert "Pages and names the API refused" in bundle

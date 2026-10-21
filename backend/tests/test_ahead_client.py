"""Ahead's HTTP caller (ADR 065): the Bearer token goes to the checked loopback address only and is never logged,
every failure maps to its state in Nova's words, and the answers are parsed strictly (a bad field names itself)."""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import pytest
import requests

import http_pool
from ahead import client
from ahead.client import ForecasterError

TOKEN = "tok-client-test-91c2"
AS_OF = "2026-10-21T09:01:00-04:00"
FIXTURES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "ahead" / "__fixtures__"


def contract_forecast(sym: str = "XYZ", as_of: str = AS_OF) -> dict:
    """A contract ``/v1/forecast`` answer built from the made-up ready fixture."""
    ai = json.loads((FIXTURES / "answer_ready.json").read_text(encoding="utf-8"))["ai"]
    return {
        "contract": "ahead-forecaster/1", "symbol": sym, "as_of": as_of, "horizon_min": 15,
        "model": {"name": "model-a", "version": "1.0"},
        "levels": ai["levels"], "close": ai["close"], "volume": ai["volume"],
        "paths": {"n": 16, "close": ai["paths"]["close"], "volume": [[1.0] * 15] * 16, "joined_by": "gaussian-copula"},
        "volume_15": ai["volume_15"], "range_15": ai["range_15"], "exam_passed": False, "compute_ms": 210,
    }


def contract_health(**over) -> dict:
    status = json.loads((FIXTURES / "status_ready.json").read_text(encoding="utf-8"))["health"]
    out = {"contract": "ahead-forecaster/1", "state": "ready", "detail": None,
           "model": {"name": "model-a", "version": "1.0", "weights_sha256": "abc"},
           "exam": status["exam"], "live": status["live"]}
    out.update(over)
    return out


class FakeResp:
    def __init__(self, status: int, body=None, *, raw: bytes | None = None, chunk: int = 4096):
        self.status_code = status
        self._raw = raw if raw is not None else json.dumps(body).encode()
        self._chunk = chunk
        self.closed = False

    def iter_content(self, size):
        for i in range(0, len(self._raw), self._chunk):
            yield self._raw[i:i + self._chunk]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, answer):
        self.answer = answer
        self.calls: list[tuple[str, str, dict]] = []
        self.trust_env = True

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NOVA_AHEAD_URL", "http://127.0.0.1:8791/")
    monkeypatch.setenv("NOVA_AHEAD_TOKEN", TOKEN)


def _session(monkeypatch, answer) -> FakeSession:
    fake = FakeSession(answer)
    monkeypatch.setattr(http_pool, "session", lambda name: fake)
    return fake


def _body() -> dict:
    return {"symbol": "XYZ", "as_of": AS_OF, "horizon_min": 15, "prior_close": None, "venue": "paper", "bars": []}


def test_forecast_sends_the_bearer_token_to_the_loopback_address_only(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    resp = FakeResp(200, contract_forecast())
    fake = _session(monkeypatch, resp)
    out = client.forecast(_body())
    method, url, kw = fake.calls[0]
    assert (method, url) == ("POST", "http://127.0.0.1:8791/v1/forecast")
    assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kw["allow_redirects"] is False and kw["stream"] is True and kw["timeout"] == 3.0
    assert kw["json"] == _body()
    assert fake.trust_env is False                     # no proxy from the environment
    assert resp.closed
    assert out["paths"]["n"] == 16 and len(out["paths"]["close"]) == 16
    assert "volume" not in out["paths"]                 # volume paths are never kept
    assert TOKEN not in caplog.text


def test_health_uses_its_own_deadline(monkeypatch):
    fake = _session(monkeypatch, FakeResp(200, contract_health()))
    out = client.health()
    assert fake.calls[0][0:2] == ("GET", "http://127.0.0.1:8791/v1/health")
    assert fake.calls[0][2]["timeout"] == 1.0
    assert out["model"] == {"name": "model-a", "version": "1.0"}     # no weights hash on the wire
    assert out["exam"]["scope"] == "Example only: made-up scope."


def test_not_set_up_sends_nothing(monkeypatch):
    monkeypatch.setenv("NOVA_AHEAD_URL", "http://10.1.2.3:8791")
    fake = _session(monkeypatch, FakeResp(200, contract_forecast()))
    with pytest.raises(ForecasterError) as err:
        client.forecast(_body())
    assert err.value.state == "not_set_up"
    assert fake.calls == []


@pytest.mark.parametrize("answer, state, words, transport", [
    (requests.Timeout("boom http://127.0.0.1:8791"), "offline", "no answer in 3 s", True),
    (requests.ConnectionError("refused"), "offline", "could not connect to the forecaster", True),
    (FakeResp(401, {"error": "UNAUTHORIZED"}), "error", "the forecaster refused Nova's token", False),
    (FakeResp(503, {"error": "WARMING"}), "warming", "The forecaster is starting up.", False),
    (FakeResp(503, {"error": "OTHER"}), "error", "the forecaster answered HTTP 503", False),
    (FakeResp(500, raw=b"oops"), "error", "the forecaster answered HTTP 500", False),
    (FakeResp(302, raw=b""), "error", "the forecaster answered HTTP 302", False),
    (FakeResp(200, raw=b"not json"), "error", "an answer Nova cannot read", False),
    (FakeResp(200, raw=b"x" * (512 * 1024 + 10), chunk=64 * 1024), "error", "an answer Nova cannot read", False),
])
def test_every_failure_maps_to_its_state(monkeypatch, caplog, answer, state, words, transport):
    caplog.set_level(logging.DEBUG)
    _session(monkeypatch, answer)
    with pytest.raises(ForecasterError) as err:
        client.forecast(_body())
    assert (err.value.state, err.value.message, err.value.transport) == (state, words, transport)
    assert TOKEN not in caplog.text
    assert "127.0.0.1" not in caplog.text                # the exception's text is never logged


def test_409_says_how_many_candles_it_needs(monkeypatch):
    _session(monkeypatch, FakeResp(409, {"error": "NOT_ENOUGH_BARS", "need": 30}))
    with pytest.raises(ForecasterError) as err:
        client.forecast(_body())
    assert (err.value.state, err.value.need) == ("not_enough_bars", 30)


def _mutate(path: str, value):
    raw = contract_forecast()
    node = raw
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[int(k)] if isinstance(node, list) else node[k]
    last = keys[-1]
    if value is _DELETE:
        del node[last]
    elif isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return raw


_DELETE = object()


@pytest.mark.parametrize("path, value, field", [
    ("contract", "ahead-forecaster/2", "contract mismatch"),
    ("symbol", "ABC", "symbol"),
    ("as_of", "2026-10-21T09:02:00-04:00", "as_of"),
    ("as_of", "not a time", "as_of"),
    ("as_of", "2026-10-21T09:01:00", "as_of"),
    ("horizon_min", 10, "horizon_min"),
    ("levels", [0.1, 0.25, 0.5, 0.75], "levels"),
    ("levels", [0.05, 0.25, 0.5, 0.75, 0.95], "levels"),
    ("levels", _DELETE, "levels"),
    ("model", _DELETE, "model"),
    ("model.version", 1, "model.version"),
    ("close", _DELETE, "close"),
    ("close", [[4.6] * 5] * 14, "close"),
    ("close.0", [4.6, 4.5, 4.6, 4.7, 4.8], "close"),          # a row out of order
    ("close.0", [0.0, 0.0, 4.6, 4.7, 4.8], "close"),          # a price at zero
    ("close.0.0", float("nan"), "close"),
    ("close.0.0", True, "close"),
    ("volume.0", [-1, 5, 6, 7, 8], "volume"),
    ("volume.0", [9, 5, 6, 7, 8], "volume"),
    ("paths", _DELETE, "paths"),
    ("paths.n", 15, "paths.n"),
    ("paths.n", 17, "paths.close"),
    ("paths.close.0", [4.6] * 14, "paths.close"),
    ("paths.close.0.3", -4.6, "paths.close"),
    ("paths.joined_by", None, "paths.joined_by"),
    ("volume_15", [1, 2, 3], "volume_15"),
    ("volume_15", [5, 4, 3, 2, 1], "volume_15"),
    ("range_15", [-0.1, 0, 0, 0, 0], "range_15"),
    ("exam_passed", "yes", "exam_passed"),
    ("exam_passed", _DELETE, "exam_passed"),
    ("compute_ms", -1, "compute_ms"),
    ("compute_ms", _DELETE, "compute_ms"),
])
def test_a_bad_field_is_an_error_naming_it(path, value, field):
    with pytest.raises(ForecasterError) as err:
        client.parse_forecast(_mutate(path, value), "XYZ", AS_OF, 15)
    assert err.value.state == "error"
    assert field in err.value.message


def test_as_of_is_compared_as_an_instant():
    raw = contract_forecast(as_of="2026-10-21T13:01:00+00:00")
    assert client.parse_forecast(raw, "XYZ", AS_OF, 15)["exam_passed"] is False


def test_levels_within_a_rounding_hair_are_taken():
    raw = _mutate("levels", [0.1 + 1e-12, 0.25, 0.5, 0.75, 0.9 - 1e-12])
    assert client.parse_forecast(raw, "XYZ", AS_OF, 15)["levels"] == [0.1, 0.25, 0.5, 0.75, 0.9]


def test_health_takes_a_missing_scope_and_nullable_live_numbers():
    raw = contract_health()
    del raw["exam"]["scope"]
    raw["live"] = {"since": None, "scored": 0, "volume_spearman": None, "range_spearman": None,
                   "band80_coverage": None}
    out = client.parse_health(raw)
    assert out["exam"]["scope"] is None
    assert out["live"]["band80_coverage"] is None
    assert client.parse_health(contract_health(exam=None))["exam"] is None


@pytest.mark.parametrize("change, field", [
    ({"contract": "other/1"}, "contract mismatch"),
    ({"state": "sleeping"}, "state"),
    ({"model": {"name": "m"}}, "model.version"),
    ({"live": {"since": None, "scored": -1, "volume_spearman": None, "range_spearman": None,
               "band80_coverage": None}}, "live.scored"),
    ({"live": {"since": None}}, "live.scored"),
    ({"exam": {"passed": "no"}}, "exam.passed"),
])
def test_a_bad_health_is_an_error_naming_the_field(change, field):
    raw = contract_health()
    raw.update(copy.deepcopy(change))
    with pytest.raises(ForecasterError) as err:
        client.parse_health(raw)
    assert field in err.value.message


def test_a_bad_exam_score_names_its_path():
    raw = contract_health()
    raw["exam"]["range"]["baseline"].pop("name")
    with pytest.raises(ForecasterError) as err:
        client.parse_health(raw)
    assert "exam.range.baseline.name" in err.value.message


def test_reset_pool_makes_new_threads():
    first = client._executor()
    client.reset_pool()
    second = client._executor()
    assert first is not second
    assert second._thread_name_prefix == "ahead-ask"
    client.reset_pool()

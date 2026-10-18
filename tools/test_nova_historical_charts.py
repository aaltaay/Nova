"""Generated-only local minute resolver and native-export delegation regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nova_historical_charts as cli  # noqa: E402
import nova_historical_resolver as resolver  # noqa: E402

DAY = "2022-02-01"
ROWS = [("DEMO", m, 10.0, 10.2, 9.8, 10.1, 100 + m) for m in (570, 571, 572, 574, 575, 576, 577, 578, 579)]
ROWS += [("OTHER", 570, 900.0, 902.0, 899.0, 901.0, 999)]


def make_day(tmp_path, rows=None):
    duckdb = pytest.importorskip("duckdb")
    root = tmp_path / "minute"
    folder = root / ("d=" + DAY)
    folder.mkdir(parents=True)
    path = folder / "part.parquet"
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE input(ticker VARCHAR,m INTEGER,o DOUBLE,h DOUBLE,l DOUBLE,c DOUBLE,v BIGINT)")
        connection.executemany("INSERT INTO input VALUES (?,?,?,?,?,?,?)", ROWS if rows is None else rows)
        connection.execute("COPY input TO ? (FORMAT PARQUET)", [str(path)])
    return root, path


def expect_error(code, action):
    with pytest.raises(resolver.HistoricalChartError) as caught:
        action()
    assert caught.value.code == code


@pytest.mark.parametrize("symbol,day", [("../DEMO", DAY), ("A/B", DAY), ("", DAY),
                                       ("DEMO", "20220201"), ("DEMO", "2022-02-30")])
def test_request_is_exact(symbol, day):
    expect_error("invalid_symbol" if symbol != "DEMO" else "invalid_date",
                 lambda: resolver.validate_request(symbol, day))


@pytest.mark.parametrize("path", ["https://example.test/data", "s3://bucket", "relative/minutes", "//host/share"])
def test_no_remote_or_relative_roots(path):
    expect_error("unsafe_path", lambda: resolver.local_path(path))


def test_traversal_is_rejected_even_when_destination_exists(tmp_path):
    expect_error("unsafe_path", lambda: resolver.local_path(tmp_path / "child" / ".."))


def test_reparse_component_is_rejected(tmp_path, monkeypatch):
    real = Path.lstat

    def reparse(path):
        info = real(path)
        if path == tmp_path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    expect_error("unsafe_path", lambda: resolver.local_path(tmp_path))


def test_exact_projection_preserves_missingness_raw_units_and_hashes(tmp_path):
    root, source = make_day(tmp_path)
    before = source.read_bytes()
    receipt = resolver.resolve_bundle(root, "DEMO", DAY, tmp_path / "bundle")
    selection = json.loads(Path(receipt["selection_path"]).read_text())
    assert set(selection) == {"schema_version", "kind", "family", "selected"}
    assert selection["kind"] == "historical_ohlcv"
    entry = selection["selected"][0]
    assert set(entry) == {"day", "ticker", "bar_projection", "annotations"}
    projection_path = Path(entry["bar_projection"]["path"])
    projection = json.loads(projection_path.read_text())
    assert set(projection) == {"day", "ticker", "time_zone", "m_semantics", "price_units",
                               "observed_source_start_m", "observed_source_end_exclusive_m", "bars"}
    assert receipt["source"]["sha256"] == resolver.file_sha256(source)
    assert receipt["selection_sha256"] == resolver.file_sha256(Path(receipt["selection_path"]))
    assert entry["bar_projection"]["sha256"] == resolver.file_sha256(projection_path)
    assert projection["time_zone"] == "America/New_York"
    assert projection["price_units"] == "raw_same_session_" + DAY
    assert [r["m"] for r in projection["bars"]] == [r[1] for r in ROWS if r[0] == "DEMO"]
    assert 573 not in [r["m"] for r in projection["bars"]]
    assert all(r["o"] == 10 for r in projection["bars"])
    assert sum(r["v"] for r in projection["bars"]) == sum(r[6] for r in ROWS if r[0] == "DEMO")
    assert source.read_bytes() == before


def test_day_missing_is_distinct_from_exact_symbol_missing(tmp_path):
    root, _ = make_day(tmp_path)
    expect_error("day_missing", lambda: resolver.resolve_bundle(root, "DEMO", "2022-02-02", tmp_path / "a"))
    expect_error("symbol_missing", lambda: resolver.resolve_bundle(root, "demo", DAY, tmp_path / "b"))
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


@pytest.mark.parametrize("row", [
    ("DEMO", None, 10, 11, 9, 10, 100), ("DEMO", -1, 10, 11, 9, 10, 100),
    ("DEMO", 1440, 10, 11, 9, 10, 100), ("DEMO", 571, 10, 9, 8, 10, 100),
    ("DEMO", 571, 10, 11, 9, 10, -1), ("DEMO", 571, 10, float("nan"), 9, 10, 100),
    ("DEMO", 571, None, 11, 9, 10, 100),
])
def test_invalid_bar_refuses_whole_bundle(tmp_path, row):
    root, _ = make_day(tmp_path, [row])
    expect_error("invalid_rows", lambda: resolver.resolve_bundle(root, "DEMO", DAY, tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_duplicate_minute_is_never_chosen_or_merged(tmp_path):
    root, _ = make_day(tmp_path, [ROWS[0], ROWS[0]])
    expect_error("invalid_rows", lambda: resolver.resolve_bundle(root, "DEMO", DAY, tmp_path / "out"))


def test_existing_output_preserved(tmp_path):
    root, _ = make_day(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserve")
    expect_error("output_exists", lambda: resolver.resolve_bundle(root, "DEMO", DAY, output))
    assert sentinel.read_text() == "preserve" and list(output.iterdir()) == [sentinel]


def test_changed_source_cannot_publish(tmp_path, monkeypatch):
    root, source = make_day(tmp_path)
    original = resolver._read_rows

    def changed(path, symbol):
        rows = original(path, symbol)
        source.write_bytes(source.read_bytes() + b"changed")
        return rows

    monkeypatch.setattr(resolver, "_read_rows", changed)
    expect_error("input_changed", lambda: resolver.resolve_bundle(root, "DEMO", DAY, tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_corrupt_local_file_is_not_a_missing_symbol(tmp_path):
    root = tmp_path / "minute"
    folder = root / ("d=" + DAY)
    folder.mkdir(parents=True)
    (folder / "part.parquet").write_bytes(b"not parquet")
    pytest.importorskip("duckdb")
    expect_error("invalid_input", lambda: resolver.resolve_bundle(root, "DEMO", DAY, tmp_path / "out"))


def gateway_fixture(tmp_path):
    gateway = tmp_path / "gateway"
    (gateway / "tools").mkdir(parents=True)
    (gateway / "tools" / "nova_charts.py").write_text("# generated fixture only\n")
    return gateway


def test_cli_delegates_to_existing_exporter_without_shell(tmp_path, monkeypatch, capsys):
    root, _ = make_day(tmp_path)
    gateway = gateway_fixture(tmp_path)
    calls = []

    def export(command, **kwargs):
        calls.append((command, kwargs))
        assert command[:3] == [sys.executable, str(gateway / "tools" / "nova_charts.py"), "export"]
        assert "--selection" in command and "--sha256" in command
        assert kwargs["cwd"] == gateway and kwargs.get("shell", False) is False
        assert kwargs["timeout"] == 180
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True, "images": [], "generated_test": True}), "")

    monkeypatch.setattr(cli.subprocess, "run", export)
    code = cli.main(["export", "--symbol", "DEMO", "--date", DAY, "--output", str(tmp_path / "out"),
                     "--massive-root", str(root), "--gateway-root", str(gateway), "--samples", "0"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result["ok"] is True and len(calls) == 1
    assert (tmp_path / "out" / "historical_export.json").is_file()
    assert result["timings"]["resolve_freeze_ms"] >= 0


@pytest.mark.parametrize("native", ["not JSON", '{"ok":false}', '[]'])
def test_cli_refuses_unverified_native_success(tmp_path, monkeypatch, native):
    root, _ = make_day(tmp_path)
    gateway = gateway_fixture(tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 0, native, ""))
    expect_error("export_failed", lambda: cli.export_historical(symbol="DEMO", day=DAY, output=tmp_path / "out",
                 massive_root=root, gateway_root=gateway))
    assert (tmp_path / "out" / "selection.json").is_file()
    assert not (tmp_path / "out" / "historical_export.json").exists()


def test_cli_timeout_preserves_bundle_and_captured_diagnostics(tmp_path, monkeypatch):
    root, _ = make_day(tmp_path)
    gateway = gateway_fixture(tmp_path)

    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 180
        raise subprocess.TimeoutExpired(command, 180, output=b"generated stdout", stderr=b"generated stderr")

    monkeypatch.setattr(cli.subprocess, "run", timeout)
    expect_error("export_timeout", lambda: cli.export_historical(symbol="DEMO", day=DAY, output=tmp_path / "out",
                 massive_root=root, gateway_root=gateway))
    assert (tmp_path / "out" / "selection.json").is_file()
    failure = json.loads((tmp_path / "out" / "native_export_failure.json").read_text())
    assert failure["stdout"] == "generated stdout" and failure["stderr"] == "generated stderr"
    assert not (tmp_path / "out" / "historical_export.json").exists()

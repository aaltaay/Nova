"""Tests for Nova OS P8 Cloudflare R2 archive durability (mocked; no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import archive.health as health
import archive.r2 as r2
import nova_os.events_db as events_db
from constants import ARCHIVE_SOURCE_IBKR


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("ARCHIVE_R2_ENABLED", raising=False)
    archive_db.init_db()
    events_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield


def _seed_and_compact(session_date: str = "2026-07-10") -> Path:
    capture.record_tape_print(
        symbol="AAPL",
        ts=1_720_000_000.0,
        price=190.0,
        size=50,
        source=ARCHIVE_SOURCE_IBKR,
        session_date=session_date,
    )
    capture.record_bar(
        symbol="AAPL",
        ts=1_720_000_000.0,
        open_=189.0,
        high=191.0,
        low=188.5,
        close=190.0,
        volume=1000,
        source=ARCHIVE_SOURCE_IBKR,
        timeframe="1m",
        session_date=session_date,
    )
    compact.compact_day(session_date)
    return compact.cold_root()


class TestR2Status:
    def test_missing_credentials_loud(self):
        status = r2.r2_status()
        assert status["configured"] is False
        assert "R2_ACCOUNT_ID" in status["missing_env"]
        assert "not configured" in status["message"].lower() or "set" in status["message"].lower()

    def test_enabled_without_keys_health_fails_loud(self, monkeypatch):
        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        snap = health.archive_health()
        assert snap["ok"] is False
        assert snap["problems"]
        assert snap["r2"]["configured"] is False

    def test_l2_bridge_failed_days_trip_top_level_health(self, monkeypatch, tmp_path):
        """L2 R2 failures must fail-loud at archive_health ok/problems (not report-only)."""
        import archive.l2_bridge as l2_bridge

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
        cold = tmp_path / "archive_cold"
        cold.mkdir(parents=True, exist_ok=True)
        l2_bridge.save_l2_verified_index(
            {"days": {"2026-07-10": {"ok": False, "error": "probe-fail"}}},
            cold_dir=cold,
        )
        snap = health.archive_health(cold_dir=cold)
        assert snap["ok"] is False
        assert "2026-07-10" in snap["l2_bridge_failed_days"]
        assert any("L2 bridge R2 upload failed" in p for p in snap["problems"])


class TestR2UploadMock:
    def test_upload_bytes_success_without_network(self, monkeypatch):
        store: dict[str, bytes] = {}

        class FakeClient:
            def head_object(self, Bucket, Key):
                if Key not in store:
                    err = Exception("404")
                    err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                    raise err
                return {"ContentLength": len(store[Key])}

            def put_object(self, Bucket, Key, Body, **kwargs):
                store[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        monkeypatch.setattr(r2, "r2_status", lambda: {
            "enabled": True,
            "configured": True,
            "boto3_available": True,
            "bucket": "nova-archive",
            "prefix": "nova-os/archive/",
            "missing_env": [],
            "message": "R2 ready",
        })
        monkeypatch.setattr(r2, "boto3_available", lambda: True)

        data = b"hello-archive"
        result = r2.upload_bytes(data, client=FakeClient(), bucket="nova-archive")
        assert result["ok"] is True
        assert result["skipped"] is False
        assert result["key"] in store

        # Second upload skips (no-overwrite)
        result2 = r2.upload_bytes(data, client=FakeClient(), bucket="nova-archive")
        assert result2["ok"] is True
        assert result2["skipped"] is True

    def test_upload_day_marks_verified(self, monkeypatch, tmp_path):
        cold = _seed_and_compact()
        store: dict[str, bytes] = {}

        class FakeClient:
            def head_object(self, Bucket, Key):
                if Key not in store:
                    err = Exception("404")
                    err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                    raise err
                return {}

            def put_object(self, Bucket, Key, Body, **kwargs):
                store[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(r2, "_client", lambda: (FakeClient(), "nova-archive"))

        result = r2.upload_day("2026-07-10", cold_dir=cold)
        assert result["ok"] is True
        assert result["verified_remote"] is True
        assert r2.is_day_verified_remote("2026-07-10", cold)

    def test_upload_never_pretends_success_when_unconfigured(self):
        result = r2.upload_bytes(b"x")
        assert result["ok"] is False
        assert result.get("configured") is False

    def test_upload_day_failure_journals_archive_upload_failed_event(self, monkeypatch):
        """A day that fails to fully upload must show up in the audit trail —
        not just a health-endpoint field nobody is actively polling."""
        from nova_os.events import KIND_SYSTEM, get_events

        cold = _seed_and_compact()

        class FailingClient:
            def head_object(self, Bucket, Key):
                err = Exception("404")
                err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                raise err

            def put_object(self, Bucket, Key, Body, **kwargs):
                raise RuntimeError("network unreachable")

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(r2, "_client", lambda: (FailingClient(), "nova-archive"))

        result = r2.upload_day("2026-07-10", cold_dir=cold)
        assert result["ok"] is False

        rows = get_events(kind=KIND_SYSTEM)
        failures = [r for r in rows if r["payload"].get("event") == "archive_upload_failed"]
        assert len(failures) == 1
        assert failures[0]["payload"]["session_date"] == "2026-07-10"
        assert failures[0]["payload"]["failed_tables"]

    def test_upload_day_missing_manifest_is_hard_failure(self, monkeypatch):
        """A crashed compact_day that never wrote one table's manifest must
        not let the day be marked verified just because the other tables'
        manifests happened to exist (the old silent `continue` bug)."""
        cold = _seed_and_compact()
        from constants import ARCHIVE_SCHEMA_VERSION

        day_dir = cold / "2026-07-10" / ARCHIVE_SCHEMA_VERSION
        (day_dir / "bars_1d.manifest.json").unlink()

        store: dict[str, bytes] = {}

        class FakeClient:
            def head_object(self, Bucket, Key):
                if Key not in store:
                    err = Exception("404")
                    err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                    raise err
                return {}

            def put_object(self, Bucket, Key, Body, **kwargs):
                store[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(r2, "_client", lambda: (FakeClient(), "nova-archive"))

        result = r2.upload_day("2026-07-10", cold_dir=cold)
        assert result["ok"] is False
        by_table = {u["table"]: u for u in result["uploads"]}
        assert by_table["bars_1d"]["ok"] is False
        assert "missing manifest" in by_table["bars_1d"]["error"]
        assert not r2.is_day_verified_remote("2026-07-10", cold)

    def test_upload_day_detects_local_payload_tamper_before_upload(self, monkeypatch):
        """If a local jsonl no longer matches its manifest's sha256 (e.g. a
        later crashed re-compaction truncated it), upload_day must refuse to
        upload it rather than let R2 "verify" stale/corrupt content."""
        from constants import ARCHIVE_SCHEMA_VERSION

        cold = _seed_and_compact()
        day_dir = cold / "2026-07-10" / ARCHIVE_SCHEMA_VERSION
        jsonl = day_dir / "tape_ibkr.jsonl"
        jsonl.write_text(jsonl.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

        store: dict[str, bytes] = {}

        class FakeClient:
            def head_object(self, Bucket, Key):
                if Key not in store:
                    err = Exception("404")
                    err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                    raise err
                return {}

            def put_object(self, Bucket, Key, Body, **kwargs):
                store[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(r2, "_client", lambda: (FakeClient(), "nova-archive"))

        result = r2.upload_day("2026-07-10", cold_dir=cold)
        assert result["ok"] is False
        by_table = {u["table"]: u for u in result["uploads"]}
        assert by_table["tape_ibkr"]["ok"] is False
        assert "sha256 mismatch" in by_table["tape_ibkr"]["error"]
        # The tampered payload must never have reached the fake bucket — no
        # "key" means upload_bytes was never called for it.
        assert "key" not in by_table["tape_ibkr"]
        assert jsonl.read_bytes() not in store.values()


class TestTrimGate:
    def test_require_verified_before_trim_still_true(self):
        from constants import ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM
        assert ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM is True
        snap = health.archive_health()
        assert snap["require_verified_before_trim"] is True
        assert snap["trim_blocked"] is True

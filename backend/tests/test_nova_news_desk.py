"""Nova News desk: fail loud, cache schema, columns, no silent empty success."""
from __future__ import annotations

from nova_news.models import ProviderResult
import nova_news.desk as desk


def _failed(pid: str, label: str) -> ProviderResult:
    return ProviderResult(
        id=pid, label=label, ok=False, count=0, error=f"{label} is down.",
    )


def _ok_story() -> ProviderResult:
    return ProviderResult(
        id="yahoo_finance",
        label="Yahoo Finance",
        ok=True,
        count=1,
        articles=[{
            "headline": "SEC charges firm after offering",
            "summary": "An 8-K followed.",
            "url": "https://finance.yahoo.com/sec-charges",
            "source": "Yahoo Finance",
            "created_at": "2026-09-11T13:00:00+00:00",
            "symbols": ["ACME"],
        }],
    )


def test_all_sources_down_no_cache_is_loud_error(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(desk, "fetch_all_providers", lambda: [
        _failed("yahoo_finance", "Yahoo Finance"),
        _failed("finnhub", "Finnhub"),
    ])
    desk.reset_for_testing()
    view = desk.build_desk(force=True)
    assert view["stories"] == []
    assert view["error"]
    assert "Yahoo Finance" in view["error"] or "Finnhub" in view["error"]
    assert view["counts"]["total"] == 0


def test_desk_builds_columns_and_persists_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(desk, "fetch_all_providers", lambda: [_ok_story()])
    desk.reset_for_testing()
    view = desk.build_desk(force=True)
    assert view["error"] is None
    assert view["schema_version"] == 1
    assert view["counts"]["total"] == 1
    assert any(view["columns"][band] for band in ("critical", "high", "watch", "background"))
    story = view["stories"][0]
    assert story["headline"].startswith("SEC charges")
    assert "yahoo" in story["tags"]
    disk = (tmp_path / "nova-news-desk.json").read_text(encoding="utf-8")
    assert '"schema_version": 1' in disk


def test_unknown_schema_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "cache_dir", lambda: tmp_path)
    (tmp_path / "nova-news-desk.json").write_text(
        '{"schema_version": 99, "as_of": 1, "stories": []}',
        encoding="utf-8",
    )
    monkeypatch.setattr(desk, "fetch_all_providers", lambda: [
        _failed("yahoo_finance", "Yahoo Finance"),
    ])
    desk.reset_for_testing()
    view = desk.build_desk(force=True)
    assert view["error"]
    assert view["stories"] == []


def test_stale_cache_used_when_live_fetch_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(desk, "fetch_all_providers", lambda: [_ok_story()])
    desk.reset_for_testing()
    first = desk.build_desk(force=True)
    assert first["stories"]

    monkeypatch.setattr(desk, "fetch_all_providers", lambda: [
        _failed("yahoo_finance", "Yahoo Finance"),
    ])
    desk._cache_ts = 0.0
    second = desk.build_desk(force=True)
    assert second["stories"]
    assert second["stories"][0]["url"] == first["stories"][0]["url"]

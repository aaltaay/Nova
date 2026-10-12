"""The company's country (operator ask, 2026-10-12): Yahoo's country name and its ISO code for the desk's flag."""
from __future__ import annotations

import pytest

import fundamentals as fund
from constants_countries import COUNTRY_NAME_ALIASES, COUNTRY_NAMES


def _clear_fundamentals_cache() -> None:
    fund._fundamentals_cache.clear()
    fund._fundamentals_cache_ts.clear()
    fund._fundamentals_cache_ttl.clear()


@pytest.mark.parametrize(
    ("name", "code"),
    [
        # Yahoo's own spellings, read 2026-10-12 (TCRT, FUTU / MGIH, NIO / JFIN, TEVA, SE, GLBS, PDD).
        ("United States", "US"),
        ("Hong Kong", "HK"),
        ("China", "CN"),
        ("Israel", "IL"),
        ("Singapore", "SG"),
        ("Greece", "GR"),
        ("Ireland", "IE"),
        ("Cayman Islands", "KY"),
        # CLDR's names and the other spellings, case, accents and punctuation aside.
        ("Hong Kong SAR China", "HK"),
        ("Czech Republic", "CZ"),
        ("Czechia", "CZ"),
        ("Turkey", "TR"),
        ("Türkiye", "TR"),
        ("St. Kitts & Nevis", "KN"),
        ("Saint Kitts and Nevis", "KN"),
        ("Côte d’Ivoire", "CI"),
        ("Cote d'Ivoire", "CI"),
        ("U.S. Virgin Islands", "VI"),
        ("british virgin islands", "VG"),
        ("  South Korea  ", "KR"),
        ("Myanmar", "MM"),
    ],
)
def test_country_code_reads_the_name(name, code):
    assert fund.country_code(name) == code


@pytest.mark.parametrize("name", [None, "", "   ", "Atlantis", "Channel Islands", 840])
def test_country_code_is_none_when_the_name_names_no_country(name):
    assert fund.country_code(name) is None


def test_every_name_and_spelling_reads_one_code():
    """No two spellings collide on one key, so no name can read another country's flag."""
    keys = [fund._country_key(n) for n in COUNTRY_NAMES.values()]
    keys += [fund._country_key(n) for n in COUNTRY_NAME_ALIASES]
    assert len(keys) == len(set(keys))
    assert set(COUNTRY_NAME_ALIASES.values()) <= set(COUNTRY_NAMES)
    assert all(len(code) == 2 and code.isupper() for code in COUNTRY_NAMES)


def test_fetch_carries_yahoos_country_and_its_code(monkeypatch):
    class _Ticker:
        info = {"longName": "Futu Holdings Limited", "country": "Hong Kong", "city": "Admiralty"}

    monkeypatch.setattr(fund.yf, "Ticker", lambda _s: _Ticker())
    _clear_fundamentals_cache()
    out = fund.fetch_fundamentals("FUTU")
    assert out["country"] == "Hong Kong"
    assert out["country_code"] == "HK"


def test_no_country_from_yahoo_is_none_not_guessed(monkeypatch):
    class _Ticker:
        info = {"longName": "No Address Inc.", "country": ""}

    monkeypatch.setattr(fund.yf, "Ticker", lambda _s: _Ticker())
    _clear_fundamentals_cache()
    out = fund.fetch_fundamentals("NOADR")
    assert out["country"] is None
    assert out["country_code"] is None


def test_a_failed_read_states_no_country(monkeypatch):
    def _boom(_symbol):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(fund.yf, "Ticker", _boom)
    _clear_fundamentals_cache()
    out = fund.fetch_fundamentals("XAIR")
    assert out["country"] is None
    assert out["country_code"] is None

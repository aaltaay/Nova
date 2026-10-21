"""Ahead's gate (ADR 061): the forecaster's address must name this PC, and the token is required and never logged."""
from __future__ import annotations

import logging

import pytest

from ahead import config

TOKEN = "tok-config-test-7f3a"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("NOVA_AHEAD_URL", raising=False)
    monkeypatch.delenv("NOVA_AHEAD_TOKEN", raising=False)
    config._warned.clear()


def test_unset_is_the_default_and_says_so():
    assert config.base_url() is None
    assert config.setup_problem() == "NOVA_AHEAD_URL is not set"
    assert config.configured() is False


@pytest.mark.parametrize("url, base", [
    ("http://127.0.0.1:8791", "http://127.0.0.1:8791"),
    ("http://127.0.0.1:8791/", "http://127.0.0.1:8791"),
    ("http://localhost:8791", "http://localhost:8791"),
    ("http://[::1]:8791", "http://[::1]:8791"),
    ("https://127.0.0.1:8791", "https://127.0.0.1:8791"),
])
def test_loopback_addresses_are_taken(monkeypatch, url, base):
    monkeypatch.setenv("NOVA_AHEAD_URL", url)
    monkeypatch.setenv("NOVA_AHEAD_TOKEN", TOKEN)
    assert config.base_url() == base
    assert config.setup_problem() is None
    assert config.configured() is True


@pytest.mark.parametrize("url", [
    "http://10.0.0.5:8791",
    "http://example.com:8791",
    "http://127.0.0.1.example.com:8791",
    "ftp://127.0.0.1:8791",
    "127.0.0.1:8791",
    "http://127.0.0.1:99999",
    "http://user@evil.example:8791",
])
def test_anything_but_this_pc_is_refused(monkeypatch, caplog, url):
    monkeypatch.setenv("NOVA_AHEAD_URL", url)
    monkeypatch.setenv("NOVA_AHEAD_TOKEN", TOKEN)
    caplog.set_level(logging.DEBUG)
    assert config.base_url() is None
    assert config.setup_problem() == "NOVA_AHEAD_URL must name this PC (127.0.0.1)"
    assert TOKEN not in caplog.text


def test_a_bad_address_is_warned_about_once(monkeypatch, caplog):
    monkeypatch.setenv("NOVA_AHEAD_URL", "http://10.0.0.5:8791")
    caplog.set_level(logging.WARNING, logger="ahead.config")
    config.base_url()
    config.base_url()
    assert len([r for r in caplog.records if r.name == "ahead.config"]) == 1


def test_the_token_is_required(monkeypatch):
    monkeypatch.setenv("NOVA_AHEAD_URL", "http://127.0.0.1:8791")
    monkeypatch.setenv("NOVA_AHEAD_TOKEN", "   ")
    assert config.token() is None
    assert config.setup_problem() == "NOVA_AHEAD_TOKEN is not set"

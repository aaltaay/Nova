"""Tests for outbound alert dispatch (mocked HTTP)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from alerts import channels_store, dispatch
from alerts.channels_store import Channel, mask_secret
from alerts.discord import send_discord
from alerts.generic_webhook import send_webhook
from alerts.telegram import send_telegram
from constants import (
    ALERTS_CHANNEL_TYPE_DISCORD,
    ALERTS_CHANNEL_TYPE_TELEGRAM,
    ALERTS_CHANNEL_TYPE_WEBHOOK,
)


@pytest.fixture(autouse=True)
def _clear_status_ring():
    dispatch._status_ring.clear()
    yield
    dispatch._status_ring.clear()


def test_mask_secret_hides_most_of_value():
    assert mask_secret("abcdefghijklmnop") == "************mnop"
    assert mask_secret("ab") == "**"


def test_channel_to_public_never_returns_full_secrets():
    ch = Channel(
        id="1",
        type=ALERTS_CHANNEL_TYPE_DISCORD,
        enabled=True,
        name="test",
        webhook_url="https://discord.com/api/webhooks/secret-token",
    )
    pub = channels_store.channel_to_public(ch)
    assert "secret-token" not in json.dumps(pub)
    assert pub["webhook_url_masked"].endswith("oken")


@patch("alerts.discord.urllib.request.urlopen")
def test_send_discord_success(mock_urlopen):
    resp = MagicMock()
    resp.status = 204
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    ok, err = send_discord("https://discord.com/api/webhooks/x/y", {"content": "hi"})
    assert ok is True
    assert err is None


@patch("alerts.discord.urllib.request.urlopen")
def test_send_discord_loud_failure_on_bad_url(mock_urlopen):
    import urllib.error

    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://bad", code=404, msg="Not Found", hdrs=None, fp=None
    )
    ok, err = send_discord("https://discord.com/api/webhooks/x/y", {"content": "hi"})
    assert ok is False
    assert "404" in (err or "")


@patch("alerts.telegram.urllib.request.urlopen")
def test_send_telegram_success(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = b'{"ok": true}'
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    ok, err = send_telegram("123:ABC", "999", "hello")
    assert ok is True
    assert err is None


@patch("alerts.generic_webhook.urllib.request.urlopen")
def test_send_webhook_posts_json(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    ok, err = send_webhook("https://example.com/hook", {"type": "test"})
    assert ok is True
    assert err is None
    call_args = mock_urlopen.call_args[0][0]
    assert call_args.full_url == "https://example.com/hook"


@patch("alerts.dispatch._dispatch_to_channel")
@patch("alerts.channels_store.list_enabled_channels")
def test_dispatch_alert_fans_out(mock_list, mock_dispatch_one):
    ch1 = Channel(id="a", type=ALERTS_CHANNEL_TYPE_DISCORD, enabled=True, name="d1", webhook_url="u1")
    ch2 = Channel(id="b", type=ALERTS_CHANNEL_TYPE_WEBHOOK, enabled=True, name="w1", webhook_url="u2")
    mock_list.return_value = [ch1, ch2]
    mock_dispatch_one.side_effect = [
        {"channel_id": "a", "ok": True, "error": None},
        {"channel_id": "b", "ok": False, "error": "timeout"},
    ]

    results = dispatch.dispatch_alert({"type": "hod_momo", "alert": {"ticker": "AAPL"}})
    assert len(results) == 2
    assert mock_dispatch_one.call_count == 2
    assert results[1]["ok"] is False


@patch("alerts.channels_store.list_enabled_channels", return_value=[])
def test_dispatch_no_channels_records_error(mock_list):
    results = dispatch.dispatch_alert({"type": "hod_momo", "alert": {}})
    assert results[0]["ok"] is False
    assert dispatch.get_status()

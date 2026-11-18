"""Notifications to the phone (ADR 070, amendment 2026-11-18): the message format against the standard's own
example, what the PC keeps, the gate that decides what is sent, the words, the hand-off from the desk's
producers, and the routes behind the phone's PIN."""
from __future__ import annotations

import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import FastAPI
from fastapi.testclient import TestClient

from phone import session
from phone.constants_phone import PHONE_LOCKED, PHONE_SESSION_HEADER
from phone_notify import gate as gate_rules
from phone_notify import hooks, sender, store, vapid, webpush, words
from phone_notify.constants_phone_notify import (
    KIND_FILL,
    KIND_HOD,
    KIND_LEADER,
    KIND_LOSS_LIMIT,
    KIND_SETUP,
    KIND_TEST,
    PHONE_NOTIFY_DEFAULT_SETTINGS,
    PHONE_NOTIFY_HOD_QUIET_SEC,
    PHONE_NOTIFY_KEY_ENV,
    PHONE_NOTIFY_MAX_DEVICES,
    REASON_BAD_ADDRESS,
    REASON_BAD_SETTINGS,
    REASON_NO_DEVICE,
    REASON_NO_KEY,
    REASON_SEND_FAILED,
)
from phone_notify.routes import router
from phone_notify.tell import tell

ET = ZoneInfo("America/New_York")
# RFC 8291, section 5: the standard's worked example.
RFC_PLAINTEXT = b"When I grow up, I want to be a watermelon"
RFC_SENDER_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
RFC_SENDER_PUBLIC = "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
RFC_PHONE_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
RFC_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
RFC_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
RFC_BODY = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6Tlz"
            "AC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def at(text: str) -> float:
    """Epoch seconds of a New York wall time, "YYYY-MM-DD HH:MM"."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ET).timestamp()


WEDNESDAY_0743 = at("2026-11-18 07:43")
ON = {**PHONE_NOTIFY_DEFAULT_SETTINGS, "hod_momo": "stars", "setups": True, "new_leader": True, "fills": True,
      "loss_limit": True, "start": "07:00", "end": "11:00"}


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    """Each test has its own cache folder and its own .env, and starts with no memory of what was sent."""
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NOVA_ENV_PATH", str(tmp_path / "nova.env"))
    monkeypatch.delenv(PHONE_NOTIFY_KEY_ENV, raising=False)
    hooks.reset_for_tests()
    store.forget_for_tests()
    session.close()
    yield
    session.close()


def a_phone() -> dict[str, str]:
    """A subscription as a browser hands it over: a fresh key pair and a 16-byte secret."""
    key = webpush.new_private_key()
    return {"endpoint": ENDPOINT, "p256dh": webpush.b64url_encode(webpush.public_bytes(key.public_key())),
            "auth": webpush.b64url_encode(b"0123456789abcdef")}


# ── The message format ────────────────────────────────────────────────────────

def test_encrypt_reproduces_the_standards_worked_example():
    key = webpush.private_key_from_b64(RFC_SENDER_PRIVATE)
    assert webpush.b64url_encode(webpush.public_bytes(key.public_key())) == RFC_SENDER_PUBLIC
    body = webpush.encrypt(RFC_PLAINTEXT, webpush.b64url_decode(RFC_PHONE_PUBLIC), webpush.b64url_decode(RFC_AUTH),
                           salt=webpush.b64url_decode(RFC_SALT), sender_key=key)
    assert webpush.b64url_encode(body) == RFC_BODY


def test_every_message_is_scrambled_afresh_and_a_long_one_is_refused_not_cut():
    phone = a_phone()
    p256dh, auth = webpush.b64url_decode(phone["p256dh"]), webpush.b64url_decode(phone["auth"])
    assert webpush.encrypt(b"same words", p256dh, auth) != webpush.encrypt(b"same words", p256dh, auth)
    with pytest.raises(ValueError, match="one push holds"):
        webpush.encrypt(b"x" * 5000, p256dh, auth)
    with pytest.raises(ValueError, match="16 bytes"):
        webpush.encrypt(b"hello", p256dh, b"short")


def test_the_sending_token_names_the_push_service_and_is_signed_by_the_pcs_key():
    key = webpush.new_private_key()
    header = webpush.vapid_authorization(ENDPOINT, key, subject="https://example.test", expires_at=1_900_000_000)
    assert header.startswith("vapid t=")
    token, shown_key = header[len("vapid t="):].split(", k=")
    head, claims, signature = token.split(".")
    assert json.loads(webpush.b64url_decode(head)) == {"typ": "JWT", "alg": "ES256"}
    assert json.loads(webpush.b64url_decode(claims)) == {
        "aud": "https://fcm.googleapis.com", "exp": 1_900_000_000, "sub": "https://example.test"}
    assert shown_key == webpush.b64url_encode(webpush.public_bytes(key.public_key()))
    raw = webpush.b64url_decode(signature)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(der, f"{head}.{claims}".encode("ascii"), ec.ECDSA(hashes.SHA256()))   # raises when forged


# ── The sending key ───────────────────────────────────────────────────────────

def test_the_key_is_made_once_written_to_env_and_keeps_the_other_lines(tmp_path):
    env = tmp_path / "nova.env"
    env.write_text("NOVA_API_KEY=keep-me\n# a comment\n", encoding="utf-8")
    assert vapid.private_key() is None and vapid.public_key_b64() is None

    key, error = vapid.ensure()
    assert error is None and key is not None
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["NOVA_API_KEY=keep-me", "# a comment"]
    assert lines[2].startswith(f"{PHONE_NOTIFY_KEY_ENV}=") and len(lines) == 3

    again, error = vapid.ensure()
    assert error is None
    assert webpush.private_key_to_b64(again) == webpush.private_key_to_b64(key)
    assert len(base64.urlsafe_b64decode(vapid.public_key_b64() + "=")) == 65


def test_a_line_that_is_not_a_key_is_said_and_never_overwritten(tmp_path):
    env = tmp_path / "nova.env"
    env.write_text(f"{PHONE_NOTIFY_KEY_ENV}=not-a-key\n", encoding="utf-8")
    key, error = vapid.ensure()
    assert key is None and "not a sending key" in error
    assert env.read_text(encoding="utf-8") == f"{PHONE_NOTIFY_KEY_ENV}=not-a-key\n"


# ── What the PC keeps ─────────────────────────────────────────────────────────

def test_everything_starts_off_with_no_phone():
    assert store.settings() == PHONE_NOTIFY_DEFAULT_SETTINGS
    assert store.settings()["hod_momo"] == "off" and not any(
        store.settings()[k] for k in ("setups", "new_leader", "fills", "loss_limit"))
    assert store.devices() == []


@pytest.mark.parametrize("change, why", [
    ({"hod_momo": "loud"}, "off, stars or all"),
    ({"fills": "yes"}, "on or off"),
    ({"days": [7]}, "0 (Monday) to 6"),
    ({"days": [True]}, "0 (Monday) to 6"),
    ({"start": "7:00"}, "HH:MM"),
    ({"start": "07:10"}, "half hour"),
    ({"start": "03:30"}, "04:00 to 20:00"),
    ({"end": "20:30"}, "04:00 to 20:00"),
    ({"start": "11:00", "end": "11:00"}, "after the start"),
])
def test_settings_that_are_not_settings_are_refused_with_the_reason(change, why):
    kept, error = store.save_settings({**ON, **change})
    assert kept is None and why in error
    assert store.settings() == PHONE_NOTIFY_DEFAULT_SETTINGS


def test_settings_and_phones_survive_a_reread_and_a_phone_can_leave():
    kept, error = store.save_settings({**ON, "days": [4, 0, 0]})
    assert error is None and kept["days"] == [0, 4]
    phone = a_phone()
    assert store.add_device(phone["endpoint"], phone["p256dh"], phone["auth"], now=10.0) is None
    assert store.add_device(phone["endpoint"], phone["p256dh"], phone["auth"], now=20.0) is None   # the same phone again
    doc = json.loads(store.path().read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1 and doc["settings"]["hod_momo"] == "stars"
    assert [d["id"] for d in doc["devices"]] == [store.device_id(ENDPOINT)] and doc["devices"][0]["added_at"] == 20.0
    assert store.remove_device(ENDPOINT) is True and store.devices() == []
    assert store.remove_device(ENDPOINT) is False


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/x",              # not https
    "https://evil.example/fcm.googleapis.com",           # not a push service
    "https://fcm.googleapis.com.evil.example/x",
    "https://user:pw@fcm.googleapis.com/x",
    "https://fcm.googleapis.com:8443/x",
    "https://127.0.0.1/x",
    "",
])
def test_the_pc_only_posts_to_a_push_service(endpoint):
    phone = a_phone()
    assert store.add_device(endpoint, phone["p256dh"], phone["auth"]) is not None
    assert store.devices() == []


def test_other_browsers_push_services_are_taken_and_bad_keys_are_not():
    phone = a_phone()
    for endpoint in ("https://updates.push.services.mozilla.com/wpush/v2/x", "https://web.push.apple.com/x"):
        assert store.check_endpoint(endpoint) is None
    assert "keys" in store.add_device(ENDPOINT, "AAAA", phone["auth"])


def test_the_list_of_phones_is_short():
    phone = a_phone()
    for n in range(PHONE_NOTIFY_MAX_DEVICES):
        assert store.add_device(f"{ENDPOINT}-{n}", phone["p256dh"], phone["auth"]) is None
    assert "already" in store.add_device(f"{ENDPOINT}-one-more", phone["p256dh"], phone["auth"])


def test_a_file_of_another_version_is_not_read(caplog):
    store.path().parent.mkdir(parents=True, exist_ok=True)
    store.path().write_text(json.dumps({"schema_version": 2, "settings": {**ON}, "devices": [a_phone()]}), encoding="utf-8")
    store.forget_for_tests()
    assert store.settings() == PHONE_NOTIFY_DEFAULT_SETTINGS and store.devices() == []
    assert "schema_version 2" in caplog.text


# ── The gate ──────────────────────────────────────────────────────────────────

def star(symbol: str) -> str | None:
    return {"GP": "star", "NBIG": "auto"}.get(symbol)


def test_hours_are_new_york_time_on_the_chosen_days_and_the_end_is_not_included():
    assert gate_rules.in_hours(ON, at("2026-11-18 07:00"))
    assert gate_rules.in_hours(ON, at("2026-11-18 10:59"))
    assert not gate_rules.in_hours(ON, at("2026-11-18 11:00"))
    assert not gate_rules.in_hours(ON, at("2026-11-18 06:59"))
    assert not gate_rules.in_hours(ON, at("2026-11-21 08:00"))            # a Saturday
    assert gate_rules.in_hours({**ON, "days": [5]}, at("2026-11-21 08:00"))
    assert not gate_rules.in_hours({**ON, "days": []}, WEDNESDAY_0743)


def test_hod_momo_off_stars_all_and_running_up_never():
    hod = {"symbol": "GMM", "strategy_id": 11}
    g = gate_rules.Gate()
    assert g.decide(KIND_HOD, hod, settings={**ON, "hod_momo": "off"}, now=WEDNESDAY_0743, how=star) == "off"
    assert g.decide(KIND_HOD, hod, settings=ON, now=WEDNESDAY_0743, how=star) == "not_a_star"
    assert g.decide(KIND_HOD, {"symbol": "NBIG", "strategy_id": 11}, settings=ON, now=WEDNESDAY_0743, how=star) == "not_a_star"
    assert g.decide(KIND_HOD, {"symbol": "GP", "strategy_id": 11}, settings=ON, now=WEDNESDAY_0743, how=star) == "send"
    everyone = {**ON, "hod_momo": "all"}
    assert g.decide(KIND_HOD, hod, settings=everyone, now=WEDNESDAY_0743, how=star) == "send"
    assert g.decide(KIND_HOD, {"symbol": "GMM", "strategy_id": 12}, settings=everyone, now=WEDNESDAY_0743, how=star) == "running_up"
    assert g.decide(KIND_HOD, hod, settings=everyone, now=at("2026-11-18 11:30"), how=star) == "outside_hours"


def test_one_hod_momo_notification_per_stock_per_quiet_period_and_a_new_day_starts_clean():
    everyone = {**ON, "hod_momo": "all"}
    hod = {"symbol": "GMM", "strategy_id": 11}
    g = gate_rules.Gate()
    assert g.decide(KIND_HOD, hod, settings=everyone, now=WEDNESDAY_0743) == "send"
    assert g.decide(KIND_HOD, hod, settings=everyone, now=WEDNESDAY_0743 + 60) == "quiet"
    assert g.decide(KIND_HOD, {"symbol": "HIHO", "strategy_id": 11}, settings=everyone, now=WEDNESDAY_0743 + 60) == "send"
    assert g.decide(KIND_HOD, hod, settings=everyone, now=WEDNESDAY_0743 + PHONE_NOTIFY_HOD_QUIET_SEC) == "send"
    # A held-back alert does not restart the quiet period.
    assert g.decide(KIND_HOD, hod, settings=everyone, now=WEDNESDAY_0743 + PHONE_NOTIFY_HOD_QUIET_SEC + 30) == "quiet"
    assert g.decide(KIND_HOD, hod, settings=everyone, now=at("2026-11-19 07:01")) == "send"


def test_a_setup_notifies_once_per_stage_only_for_a_star_on_the_live_playing_scanner():
    armed = {"symbol": "GP", "stage": "armed", "setup_id": "GP-1", "source": "live", "playing": True}
    g = gate_rules.Gate()
    assert g.decide(KIND_SETUP, armed, settings=ON, now=WEDNESDAY_0743, how=star) == "send"
    assert g.decide(KIND_SETUP, armed, settings=ON, now=WEDNESDAY_0743 + 5, how=star) == "said"
    assert g.decide(KIND_SETUP, {**armed, "stage": "near"}, settings=ON, now=WEDNESDAY_0743 + 9, how=star) == "send"
    assert g.decide(KIND_SETUP, {**armed, "stage": "triggered"}, settings=ON, now=WEDNESDAY_0743 + 12, how=star) == "send"
    assert g.decide(KIND_SETUP, {**armed, "setup_id": "GP-2"}, settings=ON, now=WEDNESDAY_0743 + 20, how=star) == "send"
    fresh = gate_rules.Gate()
    assert fresh.decide(KIND_SETUP, {**armed, "stage": "leg"}, settings=ON, now=WEDNESDAY_0743, how=star) == "not_a_stage"
    assert fresh.decide(KIND_SETUP, {**armed, "source": "sim"}, settings=ON, now=WEDNESDAY_0743, how=star) == "not_live"
    assert fresh.decide(KIND_SETUP, {**armed, "playing": False}, settings=ON, now=WEDNESDAY_0743, how=star) == "not_live"
    assert fresh.decide(KIND_SETUP, {**armed, "symbol": "NBIG"}, settings=ON, now=WEDNESDAY_0743, how=star) == "not_a_star"
    assert fresh.decide(KIND_SETUP, armed, settings={**ON, "setups": False}, now=WEDNESDAY_0743, how=star) == "off"
    assert fresh.decide(KIND_SETUP, armed, settings=ON, now=at("2026-11-18 12:00"), how=star) == "outside_hours"


def test_a_new_leader_is_said_once_a_day_and_only_in_hours():
    g = gate_rules.Gate()
    assert g.decide(KIND_LEADER, {"symbol": "NBIG"}, settings=ON, now=WEDNESDAY_0743) == "send"
    assert g.decide(KIND_LEADER, {"symbol": "NBIG"}, settings=ON, now=WEDNESDAY_0743 + 3600) == "said"
    assert g.decide(KIND_LEADER, {"symbol": "NEBX"}, settings=ON, now=at("2026-11-18 15:00")) == "outside_hours"
    assert g.decide(KIND_LEADER, {"symbol": "NEBX"}, settings={**ON, "new_leader": False}, now=WEDNESDAY_0743) == "off"


def test_fills_and_the_loss_limit_come_at_any_hour_but_never_from_a_sim_replay():
    midnight = at("2026-11-21 23:30")        # a Saturday night: outside every hour chosen
    g = gate_rules.Gate()
    assert g.decide(KIND_FILL, {"symbol": "GP", "venue": "paper", "id": 7}, settings=ON, now=midnight) == "send"
    assert g.decide(KIND_FILL, {"symbol": "GP", "venue": "paper", "id": 7}, settings=ON, now=midnight) == "said"
    assert g.decide(KIND_FILL, {"symbol": "GP", "venue": "live", "id": 7}, settings=ON, now=midnight) == "send"
    assert g.decide(KIND_FILL, {"symbol": "GP", "venue": "sim", "id": 8}, settings=ON, now=midnight) == "not_this_venue"
    assert g.decide(KIND_FILL, {"symbol": "GP", "venue": "paper", "id": 9}, settings={**ON, "fills": False}, now=midnight) == "off"
    assert g.decide(KIND_LOSS_LIMIT, {"venue": "paper"}, settings=ON, now=midnight) == "send"
    assert g.decide(KIND_LOSS_LIMIT, {"venue": "sim"}, settings=ON, now=midnight) == "not_this_venue"
    assert g.decide(KIND_LOSS_LIMIT, {"venue": "live"}, settings={**ON, "loss_limit": False}, now=midnight) == "off"
    assert g.decide(KIND_TEST, {}, settings=PHONE_NOTIFY_DEFAULT_SETTINGS, now=midnight) == "send"
    assert g.decide("something_else", {}, settings=ON, now=midnight) == "unknown_kind"


# ── The words ─────────────────────────────────────────────────────────────────

ALERT = {"ticker": "GMM", "strategy_id": 11, "strategy_name": "Squeeze Alert - Up 5% in 5min", "price": 1.7089,
         "change_pct": 21.6, "rvol": 92.59, "float_shares": 559949, "volume": 13039956}


def test_a_hod_momo_notification_says_the_alerts_own_numbers():
    assert words.hod(ALERT) == {
        "title": "GMM hit HOD Momo · +21.6%",
        "body": "Up 5% in 5min · $1.71 · Vol 13.0M · RVol 93x · Float 560K",
        "tag": "hod-GMM",
        "hash": "#/trade/GMM",
    }


def test_a_fact_the_alert_does_not_carry_is_left_out_never_filled_in():
    bare = {"ticker": "LITX", "strategy_id": 13, "strategy_name": "Approaching HOD", "price": 9.8,
            "change_pct": None, "rvol": None, "float_shares": None, "volume": None}
    assert words.hod(bare) == {"title": "LITX hit HOD Momo", "body": "Approaching HOD · $9.80",
                               "tag": "hod-LITX", "hash": "#/trade/LITX"}
    assert words.price(0.678) == "0.678" and words.price(float("nan")) is None and words.price(True) is None


def test_a_setups_stage_carries_its_trigger_and_stop_even_on_a_line_that_does_not_repeat_them():
    armed = {"symbol": "GP", "setup_type": "first_pullback", "setup": {"trigger": 3.33, "stop": 3.23}, "last": 3.29}
    assert words.setup(armed, "armed") == {"title": "GP: first pullback armed", "body": "Trigger 3.33 · Stop 3.23 · Last 3.29",
                                           "tag": "setup-GP", "hash": "#/trade/GP"}
    near = {"symbol": "GP", "setup_type": "first_pullback", "last": 3.31}
    assert words.setup(near, "near", {"trigger": 3.33, "stop": 3.23})["title"] == "GP: first pullback near the trigger"
    assert words.setup(near, "near", {"trigger": 3.33, "stop": 3.23})["body"] == "Trigger 3.33 · Stop 3.23 · Last 3.31"
    assert words.setup(near, "near")["body"] == "Last 3.31"


def test_the_other_notifications():
    assert words.leader({"symbol": "NBIG", "rank": 1, "change_pct": 0.1277}, 3) == {
        "title": "NBIG joined the top 3 Gainers", "body": "Number 1 · +12.8%", "tag": "leader-NBIG", "hash": "#/trade/NBIG"}
    assert words.leader({"symbol": "NBIG"}, None)["title"] == "NBIG joined the Gainers leaders"
    bought = words.fill({"symbol": "GP", "side": "BUY", "qty": 100.0, "price": 3.21, "venue": "paper", "owner": "you", "id": 7})
    assert bought["title"] == "Filled · Bought 100 GP at 3.21" and bought["body"] == "Paper · You"
    sold = words.fill({"symbol": "GP", "side": "SLD", "qty": 50, "price": 3.4, "venue": "live", "owner": "claude", "id": "e1"})
    assert sold["title"] == "Filled · Sold 50 GP at 3.40" and sold["body"] == "Live · Claude"
    assert words.fill({"symbol": "GP", "side": "SELL", "qty": 1, "price": 3.4, "venue": "paper", "owner": None})["body"] == "Paper · Nova's own close"
    warned = words.loss_limit({"mark": "warned", "venue": "paper", "line": "you", "loss": 240.5, "limit": 300})
    assert warned == {"title": "Loss limit warning · Paper", "body": "Down $240.50 against the $300 limit · Your trades",
                      "tag": "loss-limit-paper-you", "hash": "#/account"}
    tripped = words.loss_limit({"mark": "tripped", "venue": "live", "line": "account", "loss": 305, "limit": 300, "auto_sell": True})
    assert tripped["title"] == "Loss limit reached · Live" and tripped["body"].endswith("Auto sell is closing what was opened today")
    assert words.test(WEDNESDAY_0743)["hash"] == "#/notify"


# ── The hand-off from the desk's producers ────────────────────────────────────

@pytest.fixture
def sent(monkeypatch):
    """A subscribed phone, the settings on, the hot list starring GP, and the sending captured instead of sent."""
    out: list[tuple[str, dict]] = []
    phone = a_phone()
    assert store.add_device(phone["endpoint"], phone["p256dh"], phone["auth"]) is None
    assert store.save_settings(ON)[1] is None
    monkeypatch.setattr(hooks, "_queue", lambda kind, message: out.append((kind, message)))
    monkeypatch.setattr(hooks, "_how", star)
    monkeypatch.setattr(hooks.time, "time", lambda: WEDNESDAY_0743)
    return out


def test_a_live_alert_for_a_star_is_queued_once_and_running_up_never_reads_anything(sent, monkeypatch):
    assert hooks.hod_alert({**ALERT, "ticker": "GP"}) == "send"
    assert hooks.hod_alert({**ALERT, "ticker": "GP"}) == "quiet"
    assert hooks.hod_alert(ALERT) == "not_a_star"
    monkeypatch.setattr(store, "devices", lambda: pytest.fail("Running Up must be dropped before the store is read"))
    assert hooks.hod_alert({**ALERT, "strategy_id": 12}) == "running_up"
    assert [(kind, m["title"]) for kind, m in sent] == [(KIND_HOD, "GP hit HOD Momo · +21.6%")]


def test_with_no_phone_subscribed_nothing_is_judged_or_queued(sent):
    store.remove_device(ENDPOINT)
    assert hooks.hod_alert({**ALERT, "ticker": "GP"}) == "no_phone"
    assert sent == []


def test_a_setups_lines_are_followed_from_arm_to_trigger(sent):
    base = {"symbol": "GP", "setup_type": "first_pullback", "setup_id": "GP-1", "source": "live", "playing": True}
    assert hooks.setup_line({**base, "event": "leg"}) == "not_a_stage"
    assert hooks.setup_line({**base, "event": "armed", "setup": {"trigger": 3.33, "stop": 3.23}, "last": 3.29}) == "send"
    assert hooks.setup_line({**base, "event": "near", "last": 3.31}) == "send"
    assert hooks.setup_line({**base, "event": "near", "last": 3.32}) == "said"
    assert hooks.setup_line({**base, "event": "armed", "source": "sim", "setup_id": "GP-9"}) == "not_live"
    assert [m["body"] for _kind, m in sent] == ["Trigger 3.33 · Stop 3.23 · Last 3.29", "Trigger 3.33 · Stop 3.23 · Last 3.31"]


def test_leaders_fills_and_the_loss_limit_are_handed_over(sent):
    hooks.new_leaders([{"symbol": "NBIG", "rank": 1, "change_pct": 0.1277}, {"symbol": "NEBX", "rank": 2, "change_pct": 0.1268}], 3)
    row = {"symbol": "GP", "side": "BUY", "qty": 100.0, "filled_qty": 100.0, "avg_fill_price": 3.21, "order_id": 41,
           "order_source": "manual", "order_origin": None}
    assert hooks.practice_fill(row, "paper") == "send"
    assert hooks.practice_fill(row, "paper") == "said"
    assert hooks.practice_fill(row, "sim") == "not_this_venue"
    assert hooks.practice_fill(None, "paper") == "not_this_venue"
    assert hooks.fill(symbol="GP", side="SLD", qty=1, price=3.4, venue="live", owner="you", fill_id="0001") == "send"
    assert hooks.loss_limit_mark(account="paper", line="you", mark="warned", loss=240.5, limit=300) == "send"
    assert hooks.loss_limit_mark(account="sim", line="you", mark="tripped", loss=305, limit=300) == "not_this_venue"
    assert [m["title"] for _kind, m in sent] == [
        "NBIG joined the top 3 Gainers", "NEBX joined the top 3 Gainers", "Filled · Bought 100 GP at 3.21",
        "Filled · Sold 1 GP at 3.40", "Loss limit warning · Paper"]
    assert sent[2][1]["body"] == "Paper · You"


def test_a_live_fill_is_read_inside_the_guard_whatever_ibkr_handed_over(sent):
    """Regression: the producer's line read `trade.contract` itself, so a fill object without one failed the
    Live execDetails handler before the guard ran (found by test_execution_service on this branch)."""
    from types import SimpleNamespace

    whole = SimpleNamespace(contract=SimpleNamespace(symbol="GP"))
    execution = SimpleNamespace(side="BOT", shares=1.0, price=3.21, execId="0001.01")
    assert hooks.live_fill(whole, SimpleNamespace(execution=execution)) == "send"
    assert sent[-1][1] == {"title": "Filled · Bought 1 GP at 3.21", "body": "Live · You",
                           "tag": "fill-GP-0001.01", "hash": "#/trade/GP"}
    # Nothing to read: never raised, and a fill with no stock is not a notification.
    assert hooks.live_fill(SimpleNamespace(), SimpleNamespace()) == "no_symbol"
    assert hooks.live_fill(None, None) == "no_symbol"
    # A side the fill does not carry is not called a sale.
    assert hooks.live_fill(whole, SimpleNamespace(execution=SimpleNamespace(shares=2.0, price=3.3, execId="0002"))) == "send"
    assert sent[-1][1]["title"] == "Filled · 2 GP at 3.30"
    hooks.new_leaders([{"symbol": "NBIG"}], "three")        # an N that is not a number is left out of the words
    assert sent[-1][1]["title"] == "NBIG joined the Gainers leaders"


def test_a_producer_is_never_reached_by_a_failure_here(monkeypatch, caplog):
    monkeypatch.setattr(store, "devices", lambda: (_ for _ in ()).throw(OSError("disk gone")))
    assert hooks.hod_alert(ALERT) == "error"
    monkeypatch.setattr(hooks, "practice_fill", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken")))
    tell("practice_fill", {"symbol": "GP"}, "paper")          # must not raise
    tell("no_such_hook")                                       # must not raise
    assert "could not be handed to the notifier" in caplog.text


# ── The sending ───────────────────────────────────────────────────────────────

def test_deliver_posts_a_scrambled_body_the_phone_can_read_and_forgets_a_phone_that_is_gone(monkeypatch):
    key, _ = vapid.ensure()
    phone_key = webpush.new_private_key()
    auth = b"0123456789abcdef"
    p256dh = webpush.b64url_encode(webpush.public_bytes(phone_key.public_key()))
    assert store.add_device(ENDPOINT, p256dh, webpush.b64url_encode(auth)) is None
    assert store.add_device(ENDPOINT + "-old", p256dh, webpush.b64url_encode(auth)) is None
    posts: list[tuple[str, bytes, dict]] = []

    def post(endpoint, body, headers):
        posts.append((endpoint, body, headers))
        return 410 if endpoint.endswith("-old") else 201

    monkeypatch.setattr(sender, "_post", post)
    result = sender.deliver({"title": "GMM hit HOD Momo", "body": "$1.71", "tag": "hod-GMM", "hash": "#/trade/GMM"},
                            ttl=600, now=WEDNESDAY_0743)
    assert result == {"ok": True, "sent": 1, "failed": 0, "gone": 1, "error": None}
    assert [d["endpoint"] for d in store.devices()] == [ENDPOINT]            # the gone phone left the list

    endpoint, body, headers = posts[0]
    assert headers["TTL"] == "600" and headers["Content-Encoding"] == "aes128gcm"
    assert headers["Authorization"].endswith(webpush.b64url_encode(webpush.public_bytes(key.public_key())))
    assert b"GMM" not in body                                                 # the push service cannot read it

    # Read it as the phone does (RFC 8291): the header names the sender's one-time key.
    salt, sender_public, record = body[:16], body[21:86], body[86:]
    shared = phone_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender_public))
    ikm = webpush._hkdf(auth, shared, b"WebPush: info\x00" + webpush.b64url_decode(p256dh) + sender_public, 32)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    plain = AESGCM(webpush._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)).decrypt(
        webpush._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12), record, None)
    assert json.loads(plain[:-1]) == {"title": "GMM hit HOD Momo", "body": "$1.71", "tag": "hod-GMM",
                                      "hash": "#/trade/GMM", "at": int(WEDNESDAY_0743)}


def test_a_refusal_is_a_result_with_its_reason_never_an_error(monkeypatch):
    assert sender.deliver({"title": "x"}, ttl=1)["error"] == "this PC has no sending key yet"
    vapid.ensure()
    assert sender.deliver({"title": "x"}, ttl=1)["error"] == "no phone is subscribed"
    phone = a_phone()
    store.add_device(phone["endpoint"], phone["p256dh"], phone["auth"])
    monkeypatch.setattr(sender, "_post", lambda *a: 403)
    result = sender.deliver({"title": "x"}, ttl=1)
    assert result["ok"] is False and "refused this PC's sending key (403)" in result["error"]
    assert len(store.devices()) == 1

    def unreachable(*_a):
        raise sender.requests.ConnectionError("no route")

    monkeypatch.setattr(sender, "_post", unreachable)
    assert "could not be reached" in sender.deliver({"title": "x"}, ttl=1)["error"]


# ── The routes ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def unlocked() -> dict[str, str]:
    token, _expires = session.open_session()
    return {PHONE_SESSION_HEADER: token}


def test_a_read_needs_nothing_and_shows_everything_off(client):
    body = client.get("/api/phone/notify").json()
    assert body == {"schema_version": 1, "available": True, "why_unavailable": None, "public_key": None,
                    "settings": PHONE_NOTIFY_DEFAULT_SETTINGS, "device_ids": [], "last_sent": None}


@pytest.mark.parametrize("method, path, body", [
    ("put", "/api/phone/notify/settings", ON),
    ("post", "/api/phone/notify/key", {}),
    ("post", "/api/phone/notify/subscribe", {"endpoint": ENDPOINT, "keys": {"p256dh": "x", "auth": "y"}}),
    ("post", "/api/phone/notify/unsubscribe", {"endpoint": ENDPOINT}),
    ("post", "/api/phone/notify/test", {}),
])
def test_every_write_needs_the_pins_session(client, method, path, body):
    answer = getattr(client, method)(path, json=body)
    assert answer.status_code == 401 and answer.json()["detail"]["reason"] == PHONE_LOCKED
    assert store.settings() == PHONE_NOTIFY_DEFAULT_SETTINGS and store.devices() == [] and vapid.private_key() is None


def test_turning_it_on_end_to_end(client, monkeypatch):
    headers = unlocked()
    phone = a_phone()
    wire = {"endpoint": phone["endpoint"], "keys": {"p256dh": phone["p256dh"], "auth": phone["auth"]}}

    early = client.post("/api/phone/notify/subscribe", json=wire, headers=headers)
    assert early.status_code == 409 and early.json()["detail"]["reason"] == REASON_NO_KEY

    made = client.post("/api/phone/notify/key", headers=headers).json()
    assert made["public_key"] == vapid.public_key_b64() and made["public_key"]

    joined = client.post("/api/phone/notify/subscribe", json=wire, headers=headers).json()
    assert joined["device_ids"] == [store.device_id(ENDPOINT)]

    kept = client.put("/api/phone/notify/settings", json=ON, headers=headers).json()
    assert kept["settings"] == ON

    bad = client.put("/api/phone/notify/settings", json={**ON, "end": "06:00"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"]["reason"] == REASON_BAD_SETTINGS
    assert "Nothing was changed" in bad.json()["detail"]["error"] and store.settings() == ON

    monkeypatch.setattr(sender, "_post", lambda *a: 201)
    tested = client.post("/api/phone/notify/test", headers=headers).json()
    assert tested["text"] == "Sent to 1 phone. It should arrive in a few seconds."
    assert tested["last_sent"]["ok"] is True and tested["last_sent"]["title"] == "Nova can reach this phone"

    monkeypatch.setattr(sender, "_post", lambda *a: 500)
    failed = client.post("/api/phone/notify/test", headers=headers)
    assert failed.status_code == 502 and failed.json()["detail"]["reason"] == REASON_SEND_FAILED
    assert client.get("/api/phone/notify").json()["last_sent"]["ok"] is False

    left = client.post("/api/phone/notify/unsubscribe", json={"endpoint": ENDPOINT}, headers=headers).json()
    assert left["device_ids"] == []
    none = client.post("/api/phone/notify/test", headers=headers)
    assert none.status_code == 409 and none.json()["detail"]["reason"] == REASON_NO_DEVICE


def test_a_subscription_to_anything_but_a_push_service_is_refused(client):
    headers = unlocked()
    client.post("/api/phone/notify/key", headers=headers)
    phone = a_phone()
    answer = client.post("/api/phone/notify/subscribe", headers=headers,
                         json={"endpoint": "https://attacker.example/collect", "keys": {"p256dh": phone["p256dh"], "auth": phone["auth"]}})
    assert answer.status_code == 422 and answer.json()["detail"]["reason"] == REASON_BAD_ADDRESS
    assert store.devices() == []


def test_the_real_app_lets_another_device_write_here_only_after_the_pin(monkeypatch):
    """The request guard's one door for another device (`/api/phone`) covers these routes, any method."""
    from main import app
    from request_guard.middleware import RequestGuardMiddleware
    from request_guard.policy import load_policy

    host = "desk.tail1234.ts.net"
    remote = {"host": host, "tailscale-user-login": "operator@example.com"}
    monkeypatch.setenv("NOVA_API_KEY", "the-desk-key")
    guard = next(m for m in app.user_middleware if m.cls is RequestGuardMiddleware)
    monkeypatch.setitem(guard.kwargs, "policy", load_policy({"NOVA_ALLOWED_HOSTS": host})[0])
    monkeypatch.setattr(app, "middleware_stack", None)
    try:
        real = TestClient(app)
        locked = real.put("/api/phone/notify/settings", json=ON, headers=remote)
        assert locked.status_code == 401 and locked.json()["detail"]["reason"] == PHONE_LOCKED
        ok = real.put("/api/phone/notify/settings", json=ON, headers={**remote, **unlocked()})
        assert ok.status_code == 200 and ok.json()["settings"] == ON
        assert real.get("/api/phone/notify", headers=remote).json()["settings"] == ON
    finally:
        app.middleware_stack = None  # the next test rebuilds the stack with the app's own policy


def test_the_file_is_read_once_and_a_write_is_what_the_next_read_sees(monkeypatch):
    """A fill asks the store on every fill: after the first read it is answered from memory."""
    assert store.save_settings(ON)[1] is None
    store.forget_for_tests()
    assert store.settings() == ON                      # from the file
    monkeypatch.setattr(store, "_read", lambda _file: pytest.fail("the file must not be read again"))
    assert store.settings() == ON and store.devices() == []
    phone = a_phone()
    assert store.add_device(phone["endpoint"], phone["p256dh"], phone["auth"]) is None
    assert [d["id"] for d in store.devices()] == [store.device_id(ENDPOINT)]
    # What a caller is handed is a copy: changing it changes nothing kept.
    store.settings()["fills"] = False
    assert store.settings()["fills"] is True

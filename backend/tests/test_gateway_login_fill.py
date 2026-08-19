"""IBC login id / password helpers. Never logs secrets."""
from pathlib import Path

from ibkr.gateway_login_fill import (
    align_ibc_login_id,
    classify_ibc_login_progress,
    parse_ibc_credentials,
    read_ini_key,
    write_ib_password,
    _log_suffix,
)


def test_parse_ibc_credentials_skips_comments():
    text = (
        "# IbLoginId=notme\n"
        "IbLoginId=alice\n"
        "IbPassword=p@ss+word\n"
        "TradingMode=live\n"
    )
    creds = parse_ibc_credentials(text)
    assert creds is not None
    assert creds.username == "alice"
    assert creds.password == "p@ss+word"


def test_classify_ibc_login_progress():
    assert classify_ibc_login_progress("IBC: Setting user name") == "username_set"
    assert classify_ibc_login_progress("IBC: Click button: Log In") == "clicked_login"
    assert classify_ibc_login_progress("IBC: Authenticating") == "waiting"


def test_log_suffix_ignores_old_click(tmp_path: Path):
    log = tmp_path / "IBC-x.txt"
    old = "IBC: Click button: Log In\n"
    log.write_text(old, encoding="utf-8")
    origin = (log, log.stat().st_size)
    log.write_text(old + "IBC: Setting user name\n", encoding="utf-8")
    suffix = _log_suffix(origin, tmp_path)
    assert classify_ibc_login_progress(suffix) == "username_set"


def test_write_ib_password_round_trip(tmp_path: Path):
    ini = tmp_path / "config.ini"
    ini.write_text("IbLoginId=alice\nIbPassword=old\nTradingMode=live\n", encoding="utf-8")
    assert write_ib_password(ini, "") is True
    assert parse_ibc_credentials(ini.read_text(encoding="utf-8")) is None
    assert write_ib_password(ini, "new+secret") is True
    creds = parse_ibc_credentials(ini.read_text(encoding="utf-8"))
    assert creds is not None
    assert creds.password == "new+secret"


def test_align_ibc_login_id(tmp_path: Path):
    ini = tmp_path / "config.ini"
    ini.write_text(
        "IbLoginId=paperuser\nIbLoginIdLive=liveuser\nIbLoginIdPaper=paperuser\n",
        encoding="utf-8",
    )
    align_ibc_login_id(ini, "live")
    assert read_ini_key(ini, "IbLoginId") == "liveuser"
    align_ibc_login_id(ini, "paper")
    assert read_ini_key(ini, "IbLoginId") == "paperuser"

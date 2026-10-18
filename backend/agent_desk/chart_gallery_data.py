"""Validate bounded generic historical chart inputs and convert observed minutes."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
COLORS = {"blue", "gold", "grey", "green", "red"}


def shape(value: object, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - (optional or set()):
        raise ValueError("Invalid generic chart object fields")
    return value


def integer(value: object, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def label(value: object, limit: int) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= limit
            and value == value.strip() and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def identity(entry: dict) -> tuple[str, str, int]:
    day, ticker = entry["day"], entry["ticker"]
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Invalid chart date")
    try:
        date.fromisoformat(day)
    except ValueError as error:
        raise ValueError("Invalid chart date") from error
    if not label(ticker, 32):
        raise ValueError("Invalid exact ticker identifier")
    boundary = entry.get("as_of_m")
    if "as_of_m" in entry and not integer(boundary, 0, 1440):
        raise ValueError("Invalid as-of minute boundary")
    return day, ticker, -1 if boundary is None else boundary


def annotations(values: object) -> list[dict]:
    if not isinstance(values, list) or len(values) > 32:
        raise ValueError("Expected at most32 generic annotations")
    result = []
    for value in values:
        if (not isinstance(value, dict) or not isinstance(value.get("kind"), str)
                or value["kind"] not in {"horizontal_line", "time_marker"}):
            raise ValueError("Unknown generic annotation kind")
        field = "price" if value["kind"] == "horizontal_line" else "minute"
        shape(value, {"kind", field, "label"}, {"color"})
        color = value.get("color", "blue")
        if not label(value["label"], 80) or not isinstance(color, str) or color not in COLORS:
            raise ValueError("Invalid generic annotation label/color")
        number = value[field]
        if field == "minute":
            valid = integer(number, 0, 1439)
        else:
            valid = (isinstance(number, (int, float)) and not isinstance(number, bool)
                     and math.isfinite(number) and number > 0)
        if not valid:
            raise ValueError("Invalid generic annotation value")
        result.append(dict(value))
    return result


def bars(projection: dict, entry: dict) -> list[dict]:
    shape(projection, {"day", "ticker", "m_semantics", "time_zone", "price_units",
                       "observed_source_start_m", "observed_source_end_exclusive_m", "bars"})
    if (projection["day"] != entry["day"] or projection["ticker"] != entry["ticker"]
            or projection["m_semantics"] != "minute_START"
            or projection["time_zone"] != "America/New_York"
            or projection["price_units"] != "raw_same_session_" + entry["day"]):
        raise ValueError("Projection identity/clock/units mismatch")
    first, end = projection["observed_source_start_m"], projection["observed_source_end_exclusive_m"]
    if not integer(first, 0, 1439) or not integer(end, 1, 1440) or first >= end:
        raise ValueError("Invalid observed source bounds")
    rows = projection["bars"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1440:
        raise ValueError("Expected1..1440 observed minute bars")
    midnight = datetime.fromisoformat(entry["day"]).replace(tzinfo=ET)
    previous, result = -1, []
    for raw in rows:
        shape(raw, {"m", "o", "h", "l", "c", "v"})
        minute = raw["m"]
        if not integer(minute, first, end - 1):
            raise ValueError("Unknown/out-of-range minute start")
        if minute <= previous:
            raise ValueError("Duplicate/out-of-order projection minute")
        previous = minute
        values = [raw[k] for k in ("o", "h", "l", "c", "v")]
        valid = all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in values)
        if valid:
            o, high, low, close, volume = values
            valid = min(o, high, low, close) > 0 and volume >= 0 and high >= max(o, low, close) and low <= min(o, high, close)
        if not valid:
            if "as_of_m" not in entry or minute < entry["as_of_m"]:
                raise ValueError("Invalid visible-prefix projection")
            continue
        stamp = (midnight + timedelta(minutes=minute)).astimezone(timezone.utc).isoformat()
        result.append(dict(t=stamp, o=o, h=high, l=low, c=close, v=volume))
    if not result:
        raise ValueError("No valid observed chart bars")
    return result

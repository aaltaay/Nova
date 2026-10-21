"""The Forex page's wire (ADR 061; shape in architecture/schema/forex-board.md), composed from memory only.

The market's size is the BIS survey's (labelled with its month and source, never live); every other number is IBKR's
or arithmetic on IBKR's: strength from each currency's dollar move, the sessions and Follow the sun from each one-hour
level, the dollar's futures from the other side of every future. None is estimated.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from constants_forex_board import (
    FOREX_BIS,
    FOREX_BIS_DESKS,
    FOREX_BIS_EXCHANGE_TRADED_USD,
    FOREX_BIS_INSTRUMENTS,
    FOREX_BIS_REGIONS_USD,
    FOREX_BIS_TOTAL_USD,
    FOREX_CURRENCIES,
    FOREX_HISTORY_HEADROOM,
    FOREX_MIXED_PRESSURE_PCT,
    FOREX_MIXED_STRENGTH_PCT,
    FOREX_PEGGED,
    FOREX_READ_DOLLAR_PCT,
    FOREX_READ_GROUP_PCT,
    FOREX_READ_MIN_PRICED,
    FOREX_RISKIER,
    FOREX_SAFE_HAVENS,
    FOREX_SCHEMA_VERSION,
    FOREX_SESSIONS,
)
from forex_board import clock, jobs, prices, rows
from forex_board.state import Store

HOUR = 3600.0
HEADLINES = {"safe_havens": "Safe havens bought", "risk_on": "Riskier currencies bought",
             "dollar_bought": "Dollar bought", "dollar_sold": "Dollar sold", "quiet": "Quiet"}
_DESKS_TOTAL = sum(v for _n, v in FOREX_BIS_DESKS)


def read_rule(period: str) -> str:
    g, d = FOREX_READ_GROUP_PCT[period], FOREX_READ_DOLLAR_PCT[period]
    return (f"Safe havens bought when the yen and the franc average +{g:g}% of strength or more and the riskier "
            f"currencies ({', '.join(FOREX_RISKIER)}) -{g:g}% or less; riskier currencies bought the reverse; "
            f"otherwise the dollar bought or sold at ±{d:g}%; else quiet. No read until {FOREX_READ_MIN_PRICED} "
            f"currencies have a price. {', '.join(FOREX_PEGGED)} is pegged to the dollar and never named.")


def _words(codes: Sequence[str]) -> str:
    word = {c["code"]: c["word"] for c in FOREX_CURRENCIES}
    names = [word[c] for c in codes]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def read(strength: Mapping[str, float], period: str) -> dict:
    rule = read_rule(period)
    if len(strength) < FOREX_READ_MIN_PRICED:
        return {"verdict": None, "headline": "Not enough currencies priced yet",
                "detail": f"{len(strength)} of {len(FOREX_CURRENCIES)} currencies have a price", "rose": [],
                "fell": [], "rule": rule}
    g, d = FOREX_READ_GROUP_PCT[period], FOREX_READ_DOLLAR_PCT[period]
    safe = _mean([strength[c] for c in FOREX_SAFE_HAVENS if c in strength])
    risky = _mean([strength[c] for c in FOREX_RISKIER if c in strength])
    usd = strength.get("USD", 0.0)
    if safe is not None and risky is not None and safe >= g and risky <= -g:
        verdict = "safe_havens"
    elif safe is not None and risky is not None and safe <= -g and risky >= g:
        verdict = "risk_on"
    elif usd >= d:
        verdict = "dollar_bought"
    elif usd <= -d:
        verdict = "dollar_sold"
    else:
        verdict = "quiet"
    ranked = [c for c in sorted(strength, key=lambda c: -strength[c]) if c not in FOREX_PEGGED]
    rose, fell = ranked[:3], list(reversed(ranked[-3:]))
    return {"verdict": verdict, "headline": HEADLINES[verdict], "detail": f"Money ran to {_words(rose)}",
            "rose": rose, "fell": fell, "rule": rule}


def dollar(row_by: Mapping[str, dict], strength: Mapping[str, float]) -> dict:
    usd = row_by["USD"]
    others = [c for c in strength if c != "USD"]
    moves = {c: row_by[c]["price"]["vs_usd_pct"] for c in others}
    f = usd["futures"]
    return {"strength_pct": usd["strength_pct"], "priced": len(others),
            "up_against": sum(1 for c in others if moves[c] is not None and moves[c] < 0),
            "down_against": sum(1 for c in others if moves[c] is not None and moves[c] > 0),
            "pressure_usd": f.get("pressure_usd"), "pressure_pct": f.get("pressure_pct"), "traded_usd": f.get("traded_usd"),
            "size_usd": usd["size"]["usd"], "share_pct": usd["size"]["share_pct"]}


def market() -> dict:
    desks = [{"name": n, "usd": v, "share_pct": round(v / _DESKS_TOTAL * 100.0, 1)} for n, v in FOREX_BIS_DESKS]
    covered = sum(c["bis_usd"] for c in FOREX_CURRENCIES) / (2.0 * FOREX_BIS_TOTAL_USD) * 100.0
    return {"total_usd": FOREX_BIS_TOTAL_USD, "exchange_traded_usd": FOREX_BIS_EXCHANGE_TRADED_USD,
            "covered_pct": round(covered, 1), "instruments": [{"name": n, "usd": v} for n, v in FOREX_BIS_INSTRUMENTS],
            "desks": desks,
            "regions": {k: round(v / _DESKS_TOTAL * 100.0, 1) for k, v in FOREX_BIS_REGIONS_USD.items()},
            "as_of": FOREX_BIS["as_of"], "source": FOREX_BIS["source"], "url": FOREX_BIS["url"]}


def _desk_share(session: Mapping) -> float:
    key = session["desks"]
    usd = FOREX_BIS_REGIONS_USD[key] if key in FOREX_BIS_REGIONS_USD else dict(FOREX_BIS_DESKS)[key]
    return round(usd / _DESKS_TOTAL * 100.0, 1)


def path(todays: Mapping[str, dict], fx: Mapping, now: float) -> list[dict[str, float]]:
    """Every priced currency's strength at the end of each hour of the FX day begun so far."""
    done = clock.hours_done(fx, now)
    levels = {c: prices.hour_levels(t["closes"], done, t["now"] if fx["open"] else None, t["open"])
              for c, t in todays.items()}
    opens = {c: t["open"] for c, t in todays.items()}
    per_usd = {c: t["per_usd"] for c, t in todays.items()}
    begun = max((len(v) for v in levels.values()), default=0)
    return prices.strength_path(levels, opens, per_usd, begun)


def sessions(fx: Mapping, now: float, strength_path: Sequence[Mapping[str, float]]) -> list[dict]:
    out = []
    for blk, session in zip(clock.blocks(fx), FOREX_SESSIONS, strict=True):
        h0, h1 = clock.hour_of(blk["from"], fx), clock.hour_of(blk["to"] - 1.0, fx) + 1
        state = "later" if now < blk["from"] else "now" if fx["open"] and now < blk["to"] else "done"
        moves = {}
        if strength_path:
            for code in strength_path[-1]:
                got = prices.block_change(strength_path, code, h0, h1)
                if got is not None and code not in FOREX_PEGGED:
                    moves[code] = got
        rose = max(moves.items(), key=lambda kv: kv[1], default=None)
        fell = min(moves.items(), key=lambda kv: kv[1], default=None)
        out.append({**blk, "state": state,
                    "rose": {"code": rose[0], "pct": round(rose[1], 4)} if rose and state != "later" else None,
                    "fell": {"code": fell[0], "pct": round(fell[1], 4)} if fell and state != "later" else None,
                    "desks": {"label": session["desks_label"], "share_pct": _desk_share(session)}})
    return out


def by_session(fx: Mapping, code: str, strength_path: Sequence[Mapping[str, float]]) -> dict | None:
    if not strength_path or code not in strength_path[-1]:
        return None
    out = {}
    for blk in clock.blocks(fx):
        h0, h1 = clock.hour_of(blk["from"], fx), clock.hour_of(blk["to"] - 1.0, fx) + 1
        out[blk["id"]] = prices.block_change(strength_path, code, h0, h1)
    return out


def sun(st: Store, fx: Mapping, now: float, strength_path: Sequence[Mapping[str, float]]) -> dict:
    changes = prices.changes(strength_path)
    by_hour: dict[int, dict[str, float]] = {}
    usd: dict[int, list[float]] = {}
    for cur in FOREX_CURRENCIES:
        flow = st.get(f"flow:{cur['code']}", now)
        if not flow or flow.get("fx_from") != fx["from"]:
            continue
        for h, net, traded in flow.get("hours") or []:
            h = int(h)
            if traded > 0:
                by_hour.setdefault(h, {})[cur["code"]] = round(net / traded * 100.0, 2)
                row = usd.setdefault(h, [0.0, 0.0])
                row[0] -= net
                row[1] += traded
    for h, (net, traded) in usd.items():
        by_hour[h]["USD"] = round(net / traded * 100.0, 2)
    hours = [{"t": fx["from"] + h * HOUR, "strength": changes[h], "futures": by_hour.get(h, {})}
             for h in range(len(changes))]
    tracks = [{**t, "share_pct": _desk_share(s)} for t, s in zip(clock.tracks(fx), FOREX_SESSIONS, strict=True)]
    return {"from": fx["from"], "to": fx["to"], "now": now, "hours": hours, "tracks": tracks}


def _mixed(row: Mapping) -> bool:
    p, s = (row["futures"] or {}).get("pressure_pct"), row["strength_pct"]
    if p is None or s is None:
        return False
    return abs(p) >= FOREX_MIXED_PRESSURE_PCT and abs(s) >= FOREX_MIXED_STRENGTH_PCT and (p > 0) != (s > 0)


def loading(st: Store, now: float, fx: Mapping) -> bool:
    keys = []
    if fx["open"] and any(jobs.spot_ok(st, c, now) for c in FOREX_CURRENCIES):
        keys.append("quotes")
    keys += [f"hourly:{c['code']}" for c in FOREX_CURRENCIES if jobs.spot_ok(st, c, now)]
    keys += [f"flow:{c['code']}" for c in FOREX_CURRENCIES if jobs.future_ok(st, c, now)]
    return any(st.answered_at(k) is None and st.failure(k) is None for k in keys)


def compose(st: Store, now: float, *, enabled: bool, replay_desk: bool, period: str,
            history_left: int | None = None, history_headroom: int = FOREX_HISTORY_HEADROOM) -> dict:
    fx = clock.day(now)
    quotes = st.get("quotes", now) or {}
    quotes_at = st.answered_at("quotes")
    built = [rows.currency(st, cur, now, fx, period, quotes, quotes_at) for cur in FOREX_CURRENCIES]
    out_rows = [r for r, _t in built]
    todays = {r["code"]: t for r, t in built if t is not None}
    row_by = {r["code"]: r for r in out_rows}
    moves = {r["code"]: r["price"]["vs_usd_pct"] for r in out_rows
             if r["code"] != "USD" and r["price"]["vs_usd_pct"] is not None}
    strength = prices.strengths({"USD": 0.0, **moves}) if moves else {}
    strength_path = path(todays, fx, now)
    row_by["USD"]["futures"] = rows.dollar_futures(out_rows)
    for r in out_rows:
        r["strength_pct"] = round(strength[r["code"]], 4) if r["code"] in strength else None
        r["by_session"] = by_session(fx, r["code"], strength_path)
        r["mixed"] = _mixed(r)
    ok, at, error = st.source_view()
    return {
        "schema_version": FOREX_SCHEMA_VERSION, "generated_at": now, "enabled": enabled,
        "loading": bool(enabled and ok is not False and loading(st, now, fx)), "replay_desk": replay_desk,
        "period": period,
        "fx_day": {"from": fx["from"], "to": fx["to"], "open": fx["open"], "next_open_at": fx["next_open_at"]},
        "market": market(), "read": read(strength, period), "dollar": dollar(row_by, strength),
        "sessions": sessions(fx, now, strength_path), "currencies": out_rows,
        "sun": sun(st, fx, now, strength_path),
        "sources": [{"id": "ibkr", "label": "IBKR", "ok": ok, "at": at, "error": error}],
        "budget": {"history_left": history_left, "history_headroom": history_headroom, "waiting": st.waiting_for()},
    }

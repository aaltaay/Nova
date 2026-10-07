"""The short setups' template values as the scanner's parameter types (ADR 049).

``lane_params.py``'s rule for the five short setups: the catalogue keeps values in the unit the operator types
(percent as 8, not 0.08); this is where a short template's become its detector's fractions and dollars, and its
grade's thresholds. Pure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from setup_scanner.backside import BacksideParams
from setup_scanner.bear_flag import BearFlagParams
from setup_scanner.failed_breakout import FailedBreakoutParams
from setup_scanner.lost_vwap import LostVwapParams
from setup_scanner.ssr_bounce import SsrBounceParams


def _pct(value: Any) -> float:
    return float(value) / 100.0


def _opt_pct(value: Any) -> float | None:
    return None if value is None else _pct(value)


def _risk(v: dict[str, Any]) -> dict[str, Any]:
    """The risk and entry numbers every short shares; ``stop_offset`` only where the setup has one."""
    return {"stop_cap": float(v["stop_cap"]), "min_stop": float(v["min_stop"]),
            "entry_offset": float(v["entry_offset"]), "risk_slippage": float(v["risk_slippage"]),
            "near_dollars": float(v["near_dollars"]), "near_pct": _pct(v["near_pct"])}


def _stop(v: dict[str, Any]) -> dict[str, Any]:
    return {"stop_offset": float(v["stop_offset"])}


def _macd(v: dict[str, Any]) -> dict[str, Any]:
    return {"macd_negative": bool(v["macd_negative"]), "macd_fast": int(v["macd_fast"]),
            "macd_slow": int(v["macd_slow"]), "macd_signal": int(v["macd_signal"])}


def _window(v: dict[str, Any]) -> dict[str, Any]:
    out = {"session_start": str(v["session_start"]), "entry_cutoff": str(v["entry_cutoff"]),
           "target_r": float(v["target_r"])}
    if "max_per_symbol_day" in v:
        out["max_per_symbol_day"] = int(v["max_per_symbol_day"])
    return out


def backside_params(v: dict[str, Any]) -> BacksideParams:
    return BacksideParams(
        fade_pct=_pct(v["fade_pct"]), fade_lookback=int(v["fade_lookback"]), min_bounce_bars=int(v["min_bounce_bars"]),
        max_bounce_bars=int(v["max_bounce_bars"]), max_retrace=_pct(v["max_retrace"]), ema_period=int(v["ema_period"]),
        ema_tol=_pct(v["ema_tol"]), **_macd(v), **_risk(v), **_stop(v), **_window(v),
    )


def bear_flag_params(v: dict[str, Any]) -> BearFlagParams:
    return BearFlagParams(
        pole_min_bars=int(v["pole_min_bars"]), pole_min_pct=_pct(v["pole_min_pct"]),
        pole_volume_rising=bool(v["pole_volume_rising"]), min_flag_bars=int(v["min_flag_bars"]),
        max_flag_bars=int(v["max_flag_bars"]), max_retrace=_pct(v["max_retrace"]),
        flag_volume_lighter=bool(v["flag_volume_lighter"]), ema_hold=bool(v["ema_hold"]),
        reject_green_volume_high=bool(v["reject_green_volume_high"]), max_pole_wick=_opt_pct(v.get("max_pole_wick")),
        ema_period=int(v["ema_period"]), ema_tol=_pct(v["ema_tol"]), **_macd(v), **_risk(v), **_stop(v), **_window(v),
    )


def failed_breakout_params(v: dict[str, Any]) -> FailedBreakoutParams:
    return FailedBreakoutParams(
        touch_pct=_pct(v["touch_pct"]), touch_dollars=float(v["touch_dollars"]), min_touches=int(v["min_touches"]),
        lookback=int(v["lookback"]), poke_dollars=float(v["poke_dollars"]), fail_bars=int(v["fail_bars"]),
        trigger_bars=int(v["trigger_bars"]), ema_period=int(v["ema_period"]), **_macd(v), **_risk(v), **_stop(v),
        **_window(v),
    )


def lost_vwap_params(v: dict[str, Any]) -> LostVwapParams:
    return LostVwapParams(
        open_at=str(v["open_at"]), retest_pct=_pct(v["retest_pct"]), retest_dollars=float(v["retest_dollars"]),
        ema_period=int(v["ema_period"]), **_macd(v), **_risk(v), **_stop(v), **_window(v),
    )


def ssr_bounce_params(v: dict[str, Any]) -> SsrBounceParams:
    return SsrBounceParams(
        drop_pct=_pct(v["drop_pct"]), drop_lookback=int(v["drop_lookback"]), bounce_greens=int(v["bounce_greens"]),
        arm_pct=_pct(v["arm_pct"]), cancel_min=int(v["cancel_min"]), stop_pct=_pct(v["stop_pct"]),
        stop_min=float(v["stop_min"]), round_step=float(v["round_step"]), ema_period=int(v["ema_period"]),
        **_risk(v), **_window(v),
    )


@dataclass(frozen=True)
class ShortGradeRules:
    """A short's five pillars' thresholds (ADR 049 section 10); the other two pillars have no number."""

    min_run_pct: float
    min_fade_pct: float
    borrow_mult: float


def short_grade_rules(v: dict[str, Any]) -> ShortGradeRules:
    return ShortGradeRules(min_run_pct=float(v["pillar_min_run_pct"]), min_fade_pct=float(v["pillar_min_fade_pct"]),
                           borrow_mult=float(v["pillar_borrow_mult"]))

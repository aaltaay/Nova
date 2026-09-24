"""A first-pullback template's values as the scanner's own parameter types (ADR 029).

The catalogue keeps values in the unit the operator types (percent as 5, a float
in millions); this is the one place they become the fractions and shares the
detector, the tape gate, the grade and the stock filter compute with. Pure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants_setups import SETUPS_GRADE_A, SETUPS_GRADE_B, SETUPS_GRADE_C
from setup_scanner.pullback import PullbackParams
from setup_scanner.tape_gate import GateParams

_GRADE_RANK = {SETUPS_GRADE_A: 3, SETUPS_GRADE_B: 2, SETUPS_GRADE_C: 1}


@dataclass(frozen=True)
class GradeRules:
    min_price: float
    max_price: float
    min_change_pct: float
    min_rvol: float
    max_float: float


@dataclass(frozen=True)
class StockFilter:
    min_price: float | None
    max_price: float | None
    max_float: float | None
    min_change_pct: float | None
    min_rvol: float | None
    require_catalyst: bool
    min_grade: str
    unknown_passes: bool

    @property
    def active(self) -> bool:
        return (any(v is not None for v in (self.min_price, self.max_price, self.max_float,
                                            self.min_change_pct, self.min_rvol))
                or self.require_catalyst or self.min_grade != SETUPS_GRADE_C)

    def check(self, pillars: dict[str, Any], grade: str | None) -> str | None:
        """None when the setup passes; else the plain reason it was filtered out."""
        def fact(name: str, value: Any, test, words: str) -> str | None:
            if value is None:
                return None if self.unknown_passes else f"{name} unknown ({words})"
            return None if test(value) else words

        price, float_shares = pillars.get("price"), pillars.get("float")
        checks = [
            None if self.min_price is None else fact(
                "price", price, lambda v: v >= self.min_price, f"price {_num(price)} under ${self.min_price:g}"),
            None if self.max_price is None else fact(
                "price", price, lambda v: v <= self.max_price, f"price {_num(price)} over ${self.max_price:g}"),
            None if self.max_float is None else fact(
                "float", float_shares, lambda v: v <= self.max_float,
                f"float {_millions(float_shares)} over {_millions(self.max_float)}"),
            None if self.min_change_pct is None else fact(
                "change", pillars.get("change_pct"), lambda v: v >= self.min_change_pct,
                f"up {_num(pillars.get('change_pct'))}% -- under {self.min_change_pct:g}%"),
            None if self.min_rvol is None else fact(
                "relative volume", pillars.get("rvol"), lambda v: v >= self.min_rvol,
                f"relative volume {_num(pillars.get('rvol'))}x -- under {self.min_rvol:g}x"),
        ]
        if self.require_catalyst and pillars.get("news") is not True:
            checks.append("no catalyst" if pillars.get("news") is False else "catalyst unknown")
        if _GRADE_RANK.get(grade or SETUPS_GRADE_C, 1) < _GRADE_RANK[self.min_grade]:
            checks.append(f"grade {grade or '?'} -- needs {self.min_grade}")
        failed = [c for c in checks if c]
        return "; ".join(failed) if failed else None


def _num(value: Any) -> str:
    return "?" if value is None else f"{float(value):.2f}".rstrip("0").rstrip(".")


def _millions(value: Any) -> str:
    return "?" if value is None else f"{float(value) / 1e6:.1f}M"


def _pct(value: Any) -> float:
    return float(value) / 100.0


def pullback_params(v: dict[str, Any]) -> PullbackParams:
    return PullbackParams(
        leg_pct=_pct(v["leg_pct"]), leg_window=int(v["leg_window"]), leg_lookback=int(v["leg_lookback"]),
        require_hod=bool(v["require_hod"]), min_pullback_bars=int(v["min_pullback_bars"]),
        max_pullback_bars=int(v["max_pullback_bars"]), max_retrace=_pct(v["max_retrace"]),
        ema_period=int(v["ema_period"]), ema_tol=_pct(v["ema_tol"]), macd_positive=bool(v["macd_positive"]),
        macd_fast=int(v["macd_fast"]), macd_slow=int(v["macd_slow"]), macd_signal=int(v["macd_signal"]),
        stop_cap=float(v["stop_cap"]), min_stop=float(v["min_stop"]), entry_offset=float(v["entry_offset"]),
        risk_slippage=float(v["risk_slippage"]), target_mode=str(v["target_mode"]), target_r=float(v["target_r"]),
        target_fixed=float(v["target_fixed"]), near_dollars=float(v["near_dollars"]), near_pct=_pct(v["near_pct"]),
        session_start=str(v["session_start"]), entry_cutoff=str(v["entry_cutoff"]),
        max_per_symbol_day=int(v["max_per_symbol_day"]),
    )


def gate_params(v: dict[str, Any]) -> GateParams:
    return GateParams(
        window_sec=float(v["tape_window_sec"]), stale_book_sec=float(v["tape_stale_book_sec"]),
        spread_max=float(v["spread_max"]), spread_max_pct=_pct(v["spread_max_pct"]), band=float(v["band"]),
        big_seller=float(v["big_seller"]), wall=float(v["wall"]), thin_fraction=_pct(v["thin_fraction"]),
        min_ask_prints=int(v["min_ask_prints"]), hidden_mult=float(v["hidden_mult"]), red_mult=float(v["red_mult"]),
    )


def grade_rules(v: dict[str, Any]) -> GradeRules:
    return GradeRules(min_price=float(v["pillar_min_price"]), max_price=float(v["pillar_max_price"]),
                      min_change_pct=float(v["pillar_min_change_pct"]), min_rvol=float(v["pillar_min_rvol"]),
                      max_float=float(v["pillar_max_float_m"]) * 1e6)


def stock_filter(v: dict[str, Any]) -> StockFilter:
    def opt(key: str, scale: float = 1.0) -> float | None:
        return None if v.get(key) is None else float(v[key]) * scale

    return StockFilter(min_price=opt("min_price"), max_price=opt("max_price"), max_float=opt("max_float_m", 1e6),
                       min_change_pct=opt("min_change_pct"), min_rvol=opt("min_rvol"),
                       require_catalyst=bool(v.get("require_catalyst")), min_grade=str(v.get("min_grade") or "C"),
                       unknown_passes=bool(v.get("unknown_passes", True)))


@dataclass(frozen=True)
class LaneParams:
    """Everything one lane computes with, from one template."""

    template_id: str
    template_rev: int
    params_hash: str
    name: str
    pullback: PullbackParams
    gate: GateParams
    grade: GradeRules
    stock: StockFilter
    bailout_bars: int


def lane_params(template: Any) -> LaneParams:
    v = template.values
    return LaneParams(template_id=template.id, template_rev=int(template.rev), params_hash=template.fingerprint,
                      name=template.name, pullback=pullback_params(v), gate=gate_params(v), grade=grade_rules(v),
                      stock=stock_filter(v), bailout_bars=int(v["bailout_bars"]))

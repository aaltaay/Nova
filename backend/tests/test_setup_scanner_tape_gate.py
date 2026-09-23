"""The tape gate (ADR 022): veto, wait, go and blind from Level 2 and prints."""
from __future__ import annotations

from setup_scanner.tape_gate import evaluate

NOW = 1_790_000_000.0
TRIG = 4.37


def book(bid=4.35, ask=4.37, ask_size=3_000, wall: tuple[float, float] | None = None, l1=False):
    asks = [{"price": ask, "size": ask_size}]
    if wall:
        if abs(wall[0] - ask) < 1e-9:
            asks[0]["size"] = wall[1]
        else:
            asks.append({"price": wall[0], "size": wall[1]})
    asks.append({"price": ask + 0.08, "size": 2_000})
    return {"bids": [{"price": bid, "size": 4_000}, {"price": bid - 0.01, "size": 2_000}],
            "asks": asks, "l1_fallback": l1}


def prints(side: str, n: int, size: int = 1_000, start: float = NOW - 8, exchange: str = "NSDQ"):
    return [{"ts": start + i * 0.5, "size": size, "side": side, "price": 4.37, "exchange": exchange} for i in range(n)]


def ev(books, prs):
    return evaluate(trigger=TRIG, now=NOW, books=books, prints=prs)


def test_blind_without_a_fresh_book():
    assert ev([], prints("ask", 5))["verdict"] == "blind"
    stale = ev([(NOW - 5, book())], prints("ask", 5))
    assert stale["verdict"] == "blind" and "Level 2" in stale["reasons"][0]


def test_go_on_green_with_no_wall():
    out = ev([(NOW - 9, book()), (NOW - 0.5, book())], prints("ask", 4))
    assert out["verdict"] == "go"
    assert out["metrics"]["ask_prints"] == 4 and out["metrics"]["green_flow"] is True


def test_wait_without_green_on_the_tape():
    out = ev([(NOW - 9, book()), (NOW - 0.5, book())], prints("ask", 2))
    assert out["verdict"] == "wait" and "no green" in out["reasons"][0]


def test_veto_a_wide_spread():
    out = ev([(NOW - 0.5, book(bid=4.28, ask=4.37))], prints("ask", 5))
    assert out["verdict"] == "veto" and "spread" in out["reasons"][0]


def test_veto_a_100k_seller_at_the_level():
    out = ev([(NOW - 0.5, book(wall=(4.40, 120_000)))], prints("ask", 6))
    assert out["verdict"] == "veto" and "120k-share seller at 4.40" in out["reasons"][0]


def test_wait_on_a_wall_that_is_not_thinning_then_go_when_it_is():
    small = prints("ask", 6, size=400)     # 2.4k at the ask: under 2x the 3k inside ask
    held = [(NOW - 9, book(wall=(4.40, 30_000))), (NOW - 0.5, book(wall=(4.40, 28_000)))]
    out = ev(held, small)
    assert out["verdict"] == "wait" and "not thinning" in out["reasons"][0]
    eaten = [(NOW - 9, book(wall=(4.40, 30_000))), (NOW - 0.5, book(wall=(4.40, 12_000)))]
    out = ev(eaten, small)
    assert out["verdict"] == "go"
    assert any("thinning" in r for r in out["reasons"])


def test_wait_on_a_burst_of_red():
    out = ev([(NOW - 9, book()), (NOW - 0.5, book())], prints("ask", 3) + prints("bid", 8, size=2_000))
    assert out["verdict"] == "wait" and "red" in out["reasons"][0]


def test_veto_a_hidden_seller():
    # 12k bought at the ask against a 3k inside ask, and the ask never moved.
    out = ev([(NOW - 9, book()), (NOW - 0.5, book())], prints("ask", 12))
    assert out["verdict"] == "veto" and "hidden seller" in out["reasons"][0]


def test_no_hidden_seller_when_the_ask_lifts():
    out = ev([(NOW - 9, book()), (NOW - 0.5, book(bid=4.37, ask=4.39))], prints("ask", 12))
    assert out["verdict"] == "go"


def test_off_exchange_reports_do_not_count():
    out = ev([(NOW - 9, book()), (NOW - 0.5, book())], prints("ask", 6, exchange="FINRA"))
    assert out["verdict"] == "wait" and out["metrics"]["ask_prints"] == 0


def test_prints_outside_the_window_do_not_count():
    out = ev([(NOW - 9, book()), (NOW - 0.5, book())], prints("ask", 6, start=NOW - 40))
    assert out["metrics"]["ask_prints"] == 0


def test_top_of_book_only_is_said():
    out = ev([(NOW - 9, book(l1=True)), (NOW - 0.5, book(l1=True))], prints("ask", 4))
    assert out["verdict"] == "go" and out["metrics"]["l1_only"] is True
    assert any("top of book only" in r for r in out["reasons"])

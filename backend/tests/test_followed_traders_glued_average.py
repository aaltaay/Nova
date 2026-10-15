"""The letter read twice, a glued average and one position read two ways (operator report, 2026-10-15).

CHERIF's day read -$7,296.50 at $1,000 a trade. His bar showed "RGTI 12.08" from 12:30 to 13:27 ET and the feed read
it three ways in turn: RGT 112.08 (the I read as a 1), RGTI 112.08 (the I read twice: as the ticker's last letter and
as a 1 in front of the price) and now and then RGTI 12.08. The feed took each RGTI 112.08 for an add (12.08 ->
112.08) and closed and opened the position each time the reading flipped: ten trades, eight priced against 112.08 at
-89% each. The ticker check read only the first price, and took RGTI 112.08 as read because IBKR knows no RGTII.
These trades are synthetic, shaped like that day's. Schema: architecture/schema/followed-traders.md ("The letter read
twice, and a glued average").
"""
from __future__ import annotations

import pytest

from followed_traders import exits, feed, lines, tickers, view
from followed_traders.constants_followed import FOLLOWED_NO_SUCH_TICKER
from tests.test_followed_traders_tickers import (  # noqa: F401 (the autouse fixture)
    DATE,
    PENDING,
    _at,
    _clean,
    _day,
    _epoch,
    _tapes,
    _trade,
    _ts,
)

NO_TICKER = exits.stated("unavailable", why=FOLLOWED_NO_SUCH_TICKER)


def _parsed(*trades):
    return feed.parse_day(_day(list(trades)))["trades"]


def _long(symbol, entry, entry_clock, exit_clock=None, *, price=None, adds=(), read_as=None, status=None):
    return _trade(symbol, entry, side="long", trader="CHERIF", price=price, entry_clock=entry_clock,
                  exit_clock=exit_clock, adds=adds, read_as=read_as,
                  status=status or ("closed" if exit_clock else "open"))


# -- which reads can have the letter read twice ------------------------------------------------------


@pytest.mark.parametrize("symbol, price, expected", [
    ("RGTI", 112.08, 12.08),     # live, 2026-10-15: the bar's "RGTI 12.08"
    ("SOFI", 114.03, 14.03),
    ("ABCS", 55.20, 5.20),       # S read as 5
    ("XB", 81.50, 1.50),         # B read as 8
    ("ABCDI", 112.08, 12.08),    # a five-letter ticker has no longer one, but can still be read twice
    ("RGTI", 12.08, 2.08),       # the shape alone: only IBKR's tape or the average before it says which it was
    ("RGT", 112.08, None),       # T is no letter OCR reads as a 1 (that read is the lost letter, tickers.unglued)
    ("RGTI", 105.20, None),      # "05.20" is no price the bar writes
    ("BRK.B", 812.30, None),
])
def test_doubled(symbol, price, expected):
    assert tickers.doubled(symbol, price) == expected


# -- the first price -----------------------------------------------------------------------------------


def test_the_letter_read_twice_is_corrected_on_the_tape_already_read():
    tape_at = _tapes(RGTI=_at(12.07))
    got = tickers.check({"symbol": "RGTI", "entry_price": 112.08}, tape_at)
    assert (got["state"], got["read_symbol"], got["read_price"], got["other_symbol"], got["other_price"]) == (
        "corrected", "RGTI", 112.08, "RGTI", 12.08)
    assert "RGTI 12.07" in got["why"] and "read again in front of its price" in got["why"]
    assert tape_at.asked == ["RGTI"]                      # RGTII is never asked for


def test_no_longer_ticker_no_longer_vouches_for_a_read_ten_times_the_tape():
    # The hole: RGTI 112.08, the stock 2% away from 12.08 at the entry, and IBKR knows no RGTII -- it read "as read"
    # and was priced at -89%. The letter read twice is far nearer IBKR's price than the read: unchecked, no number.
    got = tickers.check({"symbol": "RGTI", "entry_price": 112.08}, _tapes(RGTI=_at(12.33), RGTII=NO_TICKER))
    assert got["state"] == "unchecked" and "12.33" in got["why"] and "not within 1.5%" in got["why"]


def test_a_real_price_with_the_same_shape_is_as_read():
    # NEAL's real SOFI 14.03 (2026-10-14) reads "SOFI 4.03" with its letter read twice: the tape says 14.03.
    assert tickers.check({"symbol": "SOFI", "entry_price": 14.03}, _tapes(SOFI=_at(14.02)))["state"] == "as_read"
    # A fast stock 2.6% off at the entry: still as read, since 14.03 is far nearer 14.40 than 4.03 is.
    got = tickers.check({"symbol": "SOFI", "entry_price": 14.03}, _tapes(SOFI=_at(14.40), SOFII=NO_TICKER))
    assert got["state"] == "as_read"


# -- every average -------------------------------------------------------------------------------------


def test_a_glued_add_is_the_same_average_read_again():
    [trade] = _parsed(_long("RGTI", 12.08, "12:30:27", "12:31:33", price=112.08,
                            adds=[("12:31:13", 112.08, 12.08)]))
    ticker = tickers.check(trade, _tapes(RGTI=_at(12.07)))
    assert ticker["state"] == "corrected" and (ticker["other_symbol"], ticker["other_price"]) == ("RGTI", 12.08)
    assert "RGTI 112.08 at 12:31:13 ET" in ticker["why"] and "12.08" in ticker["why"]
    got = tickers.shown(trade, ticker)
    assert (got["symbol"], got["entry_price"], got["price"], got["adds"]) == ("RGTI", 12.08, 12.08, [])


def test_a_flicker_between_the_glued_and_the_true_average_is_no_add():
    flicker = [("12:40:19", 112.08, 12.08), ("12:40:25", 12.08, 112.08), ("12:40:37", 112.08, 12.08),
               ("12:40:45", 12.08, 112.08), ("12:41:59", 112.08, 12.08)]
    [trade] = _parsed(_long("RGTI", 12.08, "12:38:53", "12:42:09", price=112.08, adds=flicker))
    got = tickers.shown(trade, tickers.check(trade, _tapes(RGTI=_at(12.07))))
    assert got["price"] == 12.08 and got["adds"] == []


def test_a_real_add_is_kept_and_a_glued_one_after_it_put_back():
    adds = [("12:40:00", 12.50, 12.08), ("12:41:00", 112.60, 12.50)]   # a real add, then the next one read glued
    [trade] = _parsed(_long("RGTI", 12.08, "12:38:00", "12:45:00", price=112.60, adds=adds))
    got = tickers.shown(trade, tickers.check(trade, _tapes(RGTI=_at(12.07))))
    assert got["price"] == 12.60
    assert [(a["price"], a["prev_price"]) for a in got["adds"]] == [(12.50, 12.08), (12.60, 12.50)]


def test_real_adds_need_no_check():
    [trade] = _parsed(_long("AMOD", 1.73, "12:44:23", "13:00:00", price=1.92, adds=[("12:50:00", 1.92, 1.73)]))
    assert tickers.check(trade, _tapes()) is None          # nothing about it can be glued: no tape is asked for


def test_an_average_no_add_could_make_is_never_priced():
    [trade] = _parsed(_long("ABCD", 10.00, "10:00:00", "10:30:00", price=25.00, adds=[("10:10:00", 25.00, 10.00)]))
    ticker = tickers.check(trade, _tapes())
    assert ticker["state"] == "unchecked" and "an average no add could make" in ticker["why"]
    assert "25.00 at 10:10:00 ET after 10.00" in ticker["why"]
    body, priced = _compose([trade], lambda t: tickers.check(t, _tapes()))
    row = body["traders"][0]["closed"][0]
    assert priced == [] and row["pl"] is None and row["result"] == "unscored"


# -- one position read two ways ------------------------------------------------------------------------


RGTI_DAY = [   # the 2026-10-15 shape: one RGTI long, read three ways in turn
    _long("RGTI", 112.08, "12:30:21", "12:30:27"),
    _long("RGTI", 12.08, "12:30:27", "12:31:33", price=112.08, adds=[("12:31:13", 112.08, 12.08)],
          read_as={"symbol": "RGT", "price": 112.08, "until_ts": _ts("12:30:55")}),
    _long("RGT", 112.08, "12:31:33", "12:35:15"),
    _long("RGTI", 12.08, "12:35:15", "12:44:23", price=12.08,
          adds=[("12:44:00", 112.08, 12.08), ("12:44:10", 12.08, 112.08)]),
    _long("AMOD", 1.73, "12:44:23", "13:00:00"),           # another stock opening that same second: not joined
    _long("RGTI", 12.08, "12:44:23", "13:27:25"),
]
RGTI_TAPES = {"RGTI": _at(12.07), "RGT": _at(12.55), "AMOD": _at(1.73)}


def _compose(trades, ticker_for, *, exit_prices=None):
    day = feed.parse_day(_day(trades)) if trades and isinstance(trades[0]["entry_ts"], str) else {
        **feed.parse_day(_day([])), "trades": trades}
    priced = []

    def exit_for(t):
        priced.append(t["symbol"])
        price = (exit_prices or {}).get(t["symbol"], 12.03)
        return exits.stated("at", price=price, trade_ts=t["exit_ts"] - 1, to_ts=t["exit_ts"], source="ibkr_trades")

    body = view.compose(day, now=_epoch("15:00:00"), prices={"state": "off", "why": None},
                        now_for=lambda t: lines.now_state("off"), exit_for=exit_for, ticker_for=ticker_for)
    return body, priced


def test_one_position_read_two_ways_is_one_trade():
    body, priced = _compose(RGTI_DAY, lambda t: tickers.check(t, _tapes(**RGTI_TAPES)),
                            exit_prices={"RGTI": 12.09, "AMOD": 1.80})
    [cherif] = body["traders"]
    rows = {r["symbol"]: r for r in cherif["closed"]}
    assert len(cherif["closed"]) == 2 and set(rows) == {"RGTI", "AMOD"}
    rgti = rows["RGTI"]
    assert rgti["id"] == f"CHERIF|long|RGTI|{_epoch('12:30:21'):.0f}"       # the first part's id
    assert (rgti["entry"]["first_price"], rgti["entry"]["avg_price"], rgti["adds"]) == (12.08, 12.08, [])
    assert (rgti["entry"]["ts"], rgti["exit"]["to_ts"]) == (_epoch("12:30:21"), _epoch("13:27:25"))
    assert rgti["ticker"]["state"] == "corrected"
    assert rgti["pl"] == {"per_share": 0.01, "pct": 0.08} and rgti["result"] == "win"
    assert priced.count("RGTI") == 1                                        # one exit read: the last part's
    assert cherif["record"]["wins"] == 2 and cherif["record"]["losses"] == 0


def test_each_part_priced_as_the_feed_has_it_reads_minus_89_percent():
    # What the page showed: every part a trade of its own, priced against the feed's latest average.
    def exit_for(t):
        return exits.stated("at", price=12.09, trade_ts=t["exit_ts"] - 1, to_ts=t["exit_ts"], source="ibkr_trades")

    rows = [view.trade_row(t, DATE, now=_epoch("15:00:00"), prices={"state": "off", "why": None},
                           now_for=lambda t: lines.now_state("off"), exit_for=exit_for)
            for t in _parsed(*RGTI_DAY) if t["symbol"].startswith("RGT")]
    assert [r["pl"]["pct"] for r in rows] == [-89.21, -89.21, -89.21, 0.08, 0.08]


def test_a_part_whose_ticker_is_not_settled_is_not_joined():
    tapes = {**RGTI_TAPES, "RGT": PENDING}                  # the RGT part's check is still reading IBKR
    body, _ = _compose(RGTI_DAY, lambda t: tickers.check(t, _tapes(**tapes)), exit_prices={"RGTI": 12.09})
    symbols = [r["symbol"] for r in body["traders"][0]["closed"]]
    assert symbols.count("RGT") == 1 and symbols.count("RGTI") == 2


def test_a_close_with_a_window_or_an_open_after_it_is_not_joined():
    first = _long("RGTI", 12.08, "12:00:00", "12:10:00") | {"exit_since_ts": _ts("12:09:30")}
    then = _long("RGTI", 12.08, "12:10:00", "12:20:00")
    body, _ = _compose([first, then], lambda t: tickers.check(t, _tapes(RGTI=_at(12.07))))
    assert len(body["traders"][0]["closed"]) == 2


def test_a_record_joins_the_same_way():
    got = feed.parse_range({"from": DATE, "to": DATE, "dates": [DATE],
                            "trades": [t | {"date": DATE} for t in RGTI_DAY]})
    body = view.records(got, span="day", now=_epoch("16:00:00"),
                        exit_for=lambda t: exits.stated("at", price=12.09, trade_ts=t["exit_ts"] - 1,
                                                        to_ts=t["exit_ts"], source="ibkr_trades"),
                        ticker_for=lambda t: tickers.check(t, _tapes(**RGTI_TAPES)))
    [cherif] = body["traders"]
    assert cherif["record"]["wins"] + cherif["record"]["losses"] == 2 and len(cherif["scored"]) == 2
    assert min(p["pct"] for p in cherif["scored"]) > -1

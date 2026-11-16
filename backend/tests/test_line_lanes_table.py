"""The three lanes (ADR 071): which stock each is on, and which IBKR lines a change ends and opens."""
import pytest

from line_lanes.table import BOTS, CLAUDE, YOU, Lanes, Move, put


def test_an_empty_desk_holds_no_lines():
    lanes = Lanes()
    assert lanes.stocks() == ()
    assert lanes.on(YOU) is None
    assert not Move()


def test_opening_a_stock_opens_its_lines_and_nothing_else():
    lanes, move = put(Lanes(), YOU, "xlab ")
    assert lanes.you == "XLAB"
    assert move == Move(open=("XLAB",))


def test_your_lane_moves_at_once_the_old_stock_ends_and_the_new_one_opens():
    lanes, _ = put(Lanes(), YOU, "XLAB")
    lanes, move = put(lanes, YOU, "TGHL")
    assert lanes.you == "TGHL"
    assert move == Move(close=("XLAB",), open=("TGHL",))


def test_the_same_stock_again_changes_nothing():
    lanes, _ = put(Lanes(), YOU, "XLAB")
    again, move = put(lanes, YOU, "XLAB")
    assert again == lanes
    assert not move


def test_no_owner_ever_changes_anothers_lane():
    lanes = Lanes(you="XLAB", claude="LUNR", bots="AIMD")
    after, move = put(lanes, YOU, "TGHL")
    assert (after.claude, after.bots) == ("LUNR", "AIMD")
    assert move == Move(close=("XLAB",), open=("TGHL",))
    assert len(after.stocks()) == 3


def test_a_stock_two_owners_watch_is_one_pair_of_lines():
    lanes, _ = put(Lanes(), BOTS, "XLAB")
    lanes, move = put(lanes, YOU, "XLAB")
    assert not move                                  # the bots' lines are already up
    assert lanes.stocks() == ("XLAB",)
    assert lanes.owners_of("xlab") == (YOU, BOTS)


def test_leaving_a_shared_stock_never_ends_the_other_owners_lines():
    lanes = Lanes(you="XLAB", bots="XLAB")
    after, move = put(lanes, YOU, "TGHL")
    assert move == Move(open=("TGHL",))             # XLAB stays up for the bots
    assert after.owners_of("XLAB") == (BOTS,)


def test_an_emptied_lane_ends_its_lines_and_stays_empty():
    lanes = Lanes(you="XLAB", claude="LUNR")
    after, move = put(lanes, CLAUDE, None)
    assert after.claude is None
    assert move == Move(close=("LUNR",))
    assert after.stocks() == ("XLAB",)               # nobody takes the empty lane


def test_an_unknown_owner_is_refused():
    with pytest.raises(ValueError):
        put(Lanes(), "auto_record", "XLAB")

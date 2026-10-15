"""A replay's prints held as columns (operator ask 2026-10-14): equal to the dicts they came from, in a fraction
of the room."""
from __future__ import annotations

import json
import math
import struct
import sys
import tracemalloc

import pytest

from sim.history_quotes import QuoteSeries
from sim.print_table import PrintTable, pack_columns, unpack_columns


def massive(i: int, *, conds: str = "12", sets: bool = True) -> dict:
    """A print as ``massive_files.trade`` makes one."""
    ns = 1_786_531_500_000_000_000 + i * 1_000_000
    return dict(ts=ns / 1e9, ns=ns, symbol="OFAL", price=1.6 + i / 1000, size=float(100 + i), exchange="EDGX",
                exchange_id=8, conditions=conds, correction=0, trf_id=0, sequence=362_427 + i, tape=3,
                sets_price=sets, unreported=False)


def ibkr(i: int, *, unreported: bool = False) -> dict:
    """A print as an IBKR download stores one: a whole-second ``ts`` int, no ``ns``."""
    return {"ts": 1_789_718_400 + i, "symbol": "IMCC", "price": 1.85, "size": 200.0, "exchange": "DRCTEDGE",
            "conditions": "  T ", "past_limit": False, "unreported": unreported, "seq": i}


def test_every_print_comes_back_equal_with_its_keys_in_order():
    rows = [massive(i) for i in range(5)] + [ibkr(i) for i in range(3)]
    table = PrintTable(rows)
    assert len(table) == 8 and list(table) == rows
    assert [list(row) for row in table] == [list(row) for row in rows]
    assert table[-1] == rows[-1] and table[2:4] == rows[2:4]
    assert type(table[5]["ts"]) is int and type(table[0]["ts"]) is float     # an int stays an int
    assert table[5]["unreported"] is False and table[0]["sets_price"] is True  # a bool stays a bool
    with pytest.raises(IndexError):
        table[8]


def test_odd_values_are_kept_as_they_are():
    rows = [{"ts": 1.0, "price": None, "size": 5, "sequence": None, "tags": ["a", "b"], "ns": 2 ** 70},
            {"ts": 2.0, "price": "n/a", "seq": True}]
    table = PrintTable(rows)
    assert list(table) == rows
    first = table[0]
    first["tags"].append("c")                                   # a list is a fresh copy every read
    assert table[0]["tags"] == ["a", "b"]
    assert math.isnan(table.value("price", 0)) and table.value("ns", 0) == 0   # not in a column: NaN / 0 there


def test_a_view_of_the_price_setting_prints_shares_the_columns():
    rows = [massive(i, sets=i % 3 != 0) for i in range(9)]
    table = PrintTable(rows)
    priced = table.where_fields(lambda fields: fields.get("sets_price"))
    assert list(priced) == [row for row in rows if row["sets_price"]]
    assert list(priced.values("price")) == [row["price"] for row in rows if row["sets_price"]]
    assert priced.value("price", -1) == rows[-1]["price"]
    assert table.judged(lambda fields: fields["exchange"]) == ["EDGX"] * 9
    with pytest.raises(TypeError):
        priced.append(massive(9))


def test_copies_sort_trim_and_number_rows():
    rows = [massive(i) for i in range(6)]
    shuffled = PrintTable([rows[i] for i in (3, 0, 5, 1, 4, 2)])
    ordered = shuffled.sorted_by("ns", "sequence")
    assert list(ordered) == rows
    assert ordered.sorted_by("ns", "sequence") is ordered                     # already in order: no copy
    assert list(ordered.span(1, 3)) == rows[1:3]
    assert list(shuffled.within(rows[2]["ts"], rows[4]["ts"])) == [rows[3], rows[2]]
    numbered = ordered.numbered("seq")
    assert [row["seq"] for row in numbered] == list(range(6))
    assert list(numbered)[0] == dict(rows[0], seq=0)


def test_a_table_packs_into_one_blob_and_back():
    rows = [massive(i, conds="12,37" if i % 2 else "12") for i in range(50)] + [ibkr(1, unreported=True)]
    blob = PrintTable(rows).pack()
    again = PrintTable.unpack(blob)
    assert list(again) == rows and list(again)[-1]["unreported"] is True
    view = PrintTable(rows).where_fields(lambda fields: fields.get("conditions") == "12")
    assert list(PrintTable.unpack(view.pack())) == list(view)


def test_a_blob_of_another_order_or_version_is_handled():
    from array import array

    columns, extra = unpack_columns(pack_columns({"x": array("d", [1.5, 2.5])}, {"k": 1}))
    assert list(columns["x"]) == [1.5, 2.5] and extra == {"k": 1}
    swapped = array("d", [1.5, 2.5])
    swapped.byteswap()                                                         # written on a machine of the other order
    head = json.dumps(dict(schema_version=1, byteorder="big" if sys.byteorder == "little" else "little",
                           columns=[["x", "d", 2]], extra={})).encode()
    blob = struct.pack("<I", len(head)) + head + swapped.tobytes()
    assert list(unpack_columns(blob)[0]["x"]) == [1.5, 2.5]
    with pytest.raises(ValueError, match="version"):
        unpack_columns(pack_columns({}, {}).replace(b'"schema_version":1', b'"schema_version":9'))
    with pytest.raises(ValueError, match="cut short"):
        unpack_columns(pack_columns({"x": array("d", [1.0, 2.0])}, {})[:-4])


def test_a_print_costs_a_fraction_of_a_dict():
    rows = [massive(i) for i in range(20_000)]
    tracemalloc.start()
    table = PrintTable(rows)
    held, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(table) == 20_000 and held / len(table) < 80                    # a dict of these was about 736


def test_quotes_slice_sort_and_pack():
    rows = [(10.0, 1.0, 100.0, 12, 1.1, 200.0, 12), (11.0, None, None, 0, 1.2, 50.0, 8),
            (12.0, 1.05, 10.0, 12, 1.1, 20.0, 12), (13.0, 1.06, 10.0, 12, 1.1, 20.0, 12)]
    series = QuoteSeries(row + ("conds", "ind") for row in rows)               # the files' extra fields are dropped
    assert series.rows() == rows
    assert series.between(11.5, 13.0).rows() == rows[1:3]                     # the one standing at 11.5 first
    assert series.between(9.0, 10.5).rows() == rows[:1]
    assert QuoteSeries(rows[::-1]).in_time_order().rows() == rows
    assert QuoteSeries.unpack(series.pack()).rows() == rows
    assert series.within(11.0, 13.0).rows() == rows[1:3]

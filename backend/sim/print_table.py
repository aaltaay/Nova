"""A replay's prints held as columns (operator ask 2026-10-14: "make a replay hold trades compactly").

One dict per print cost about 736 bytes and 18 microseconds to build: OFAL's 2026-08-12 had 728,489 trades,
more than a replay held (500,000 then), and 430,966 of them took 7.7 s to become dicts. Here a print is

- ``ts``, ``price``, ``size`` (float) and ``ns``, ``sequence``, ``seq`` (int) in arrays, 8 bytes each;
- the rest of it (``symbol``, ``exchange``, ``conditions``, ``sets_price``...) as one code into the distinct
  combinations of those fields the table holds -- a stock-day has a few dozen.

About 52 bytes a print. A print is a dict again only when a reader asks for one (``table[i]``, a slice,
iteration) -- the tape's last 200, never the day -- and it equals the dict it was built from, its keys in the
same order. A field a print lacks stays absent. A value that is not a number of its column's kind (``None``,
text, a bool) is kept with the rest instead, so nothing is coerced; ``values`` reads NaN (float) or 0 (int)
for such a row, and the readers that walk columns read ``ts`` / ``price`` / ``size`` only, which every print
carries as a number.

``subset`` / ``where_fields`` are views of some rows sharing the columns (a replay's price-setting prints);
``take`` / ``span`` / ``within`` copy rows into a table of their own. ``pack`` / ``unpack`` turn a table into
one blob and back for the Massive store (``pack_columns``: a JSON header, then each column's bytes).
"""
from __future__ import annotations

import json
import struct
import sys
from array import array
from collections.abc import Callable, Iterable, Iterator

FLOAT_COLUMNS = ("ts", "price", "size")
INT_COLUMNS = ("ns", "sequence", "seq")
_FLOATS, _INTS = frozenset(FLOAT_COLUMNS), frozenset(INT_COLUMNS)
# How a shape keeps one field: the value itself, or which column holds it.
_LITERAL, _FLOAT, _INT_AS_FLOAT, _INT, _JSON = 0, 1, 2, 3, 4
_EXACT_IN_FLOAT = 2 ** 53
_INT64 = (-(2 ** 63), 2 ** 63 - 1)
_NAN = float("nan")
_SCALARS = (str, int, float, bool)   # kept as they are; anything else as JSON
_POSITIONS = "I"                     # a view's rows: 4 bytes each
PACK_SCHEMA_VERSION = 1


def _kind(key: str, value) -> int:
    if type(value) is bool:
        return _LITERAL
    if key in _FLOATS:
        if type(value) is float:
            return _FLOAT
        if type(value) is int and -_EXACT_IN_FLOAT <= value <= _EXACT_IN_FLOAT:
            return _INT_AS_FLOAT
    elif key in _INTS and type(value) is int and _INT64[0] <= value <= _INT64[1]:
        return _INT
    return _LITERAL


class PrintTable:
    """Prints in columns; see the module docstring."""

    __slots__ = ("_cols", "_code", "_shapes", "_codes", "_rows")

    def __init__(self, rows: Iterable[dict] = ()):
        self._cols = {name: array("d") for name in FLOAT_COLUMNS}
        self._cols.update({name: array("q") for name in INT_COLUMNS})
        self._code = array("I")
        self._shapes: list[tuple] = []
        self._codes: dict[tuple, int] = {}
        self._rows: array | None = None          # a view's positions in the shared columns
        self.extend(rows)

    # -- building ---------------------------------------------------------------------------------------------
    def append(self, row: dict) -> None:
        if self._rows is not None:
            raise TypeError("a view of a print table is read-only")
        shape, numbers = [], {}
        for key, value in row.items():
            kind = _kind(key, value)
            if kind != _LITERAL:
                numbers[key] = value
                shape.append((key, kind, None))
            elif value is None or type(value) in _SCALARS:
                shape.append((key, _LITERAL, value))
            else:                                 # a list, a dict...: kept as JSON, a fresh copy on every read
                shape.append((key, _JSON, json.dumps(value, sort_keys=True)))
        cols = self._cols
        for name in FLOAT_COLUMNS:
            cols[name].append(float(numbers[name]) if name in numbers else _NAN)
        for name in INT_COLUMNS:
            cols[name].append(numbers.get(name, 0))
        self._code.append(self._intern(tuple(shape)))

    def extend(self, rows: Iterable[dict]) -> None:
        for row in rows:
            self.append(row)

    def _intern(self, shape: tuple) -> int:
        code = self._codes.get(shape)
        if code is None:
            code = self._codes[shape] = len(self._shapes)
            self._shapes.append(shape)
        return code

    # -- reading -----------------------------------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._code) if self._rows is None else len(self._rows)

    def _at(self, i: int) -> int:
        return i if self._rows is None else self._rows[i]

    def _row(self, j: int) -> dict:
        cols, out = self._cols, {}
        for key, kind, value in self._shapes[self._code[j]]:
            if kind == _LITERAL:
                out[key] = value
            elif kind == _FLOAT or kind == _INT:
                out[key] = cols[key][j]
            elif kind == _INT_AS_FLOAT:
                out[key] = int(cols[key][j])
            else:
                out[key] = json.loads(value)
        return out

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self._row(self._at(k)) for k in range(*i.indices(len(self)))]
        n = len(self)
        if i < 0:
            i += n
        if not 0 <= i < n:
            raise IndexError("print index out of range")
        return self._row(self._at(i))

    def __iter__(self) -> Iterator[dict]:
        for k in range(len(self)):
            yield self._row(self._at(k))

    def value(self, name: str, i: int) -> float | int:
        """One row's ``name`` column (see ``values``)."""
        return self._cols[name][self._at(i if i >= 0 else i + len(self))]

    def values(self, name: str, lo: int = 0, hi: int | None = None) -> array:
        """Rows ``lo``..``hi`` of one column: NaN (float) / 0 (int) where a row keeps that field with the rest."""
        col = self._cols[name]
        hi = len(self) if hi is None else hi
        if self._rows is None:
            return col[lo:hi]
        return array(col.typecode, (col[j] for j in self._rows[lo:hi]))

    # -- views and copies --------------------------------------------------------------------------------------
    def subset(self, positions: Iterable[int]) -> PrintTable:
        """A read-only view of the rows at ``positions`` (in this table), sharing the columns."""
        view = PrintTable.__new__(PrintTable)
        view._cols, view._code, view._shapes, view._codes = self._cols, self._code, self._shapes, self._codes
        view._rows = array(_POSITIONS, (self._at(k) for k in positions))
        return view

    @staticmethod
    def _rest(shape: tuple) -> dict:
        return {key: json.loads(value) if kind == _JSON else value
                for key, kind, value in shape if kind in (_LITERAL, _JSON)}

    def judged(self, judge: Callable[[dict], object]) -> list:
        """``judge`` of every row's fields kept with the rest -- every field but the number columns -- one result
        per row, judged once per distinct combination, never per print."""
        results = [judge(self._rest(shape)) for shape in self._shapes]
        code = self._code
        return [results[code[self._at(k)]] for k in range(len(self))]

    def where_fields(self, keep: Callable[[dict], object]) -> PrintTable:
        """A view of the rows whose fields kept with the rest pass ``keep`` (see ``judged``); the table itself when
        every combination passes (no pass over the rows)."""
        passes = [bool(keep(self._rest(shape))) for shape in self._shapes]
        if all(passes):
            return self
        code = self._code
        return self.subset(k for k in range(len(self)) if passes[code[self._at(k)]])

    def take(self, positions: Iterable[int]) -> PrintTable:
        """A table of its own holding the rows at ``positions``, in that order."""
        at = array(_POSITIONS, (self._at(k) for k in positions))
        out = PrintTable()
        out._shapes, out._codes = list(self._shapes), dict(self._codes)
        for name, col in self._cols.items():
            out._cols[name] = array(col.typecode, (col[j] for j in at))
        out._code = array("I", (self._code[j] for j in at))
        return out

    def span(self, lo: int, hi: int) -> PrintTable:
        """Rows ``lo``..``hi`` as a table of their own (a base table: a straight copy of each column)."""
        if self._rows is not None:
            return self.take(range(lo, hi))
        out = PrintTable()
        out._shapes, out._codes = list(self._shapes), dict(self._codes)
        for name, col in self._cols.items():
            out._cols[name] = col[lo:hi]
        out._code = self._code[lo:hi]
        return out

    def within(self, start: float, end: float) -> PrintTable:
        """The rows with ``start <= ts < end``, in table order, as a table of their own."""
        ts = self._cols["ts"]
        return self.take(k for k in range(len(self)) if start <= ts[self._at(k)] < end)

    def sorted_by(self, *names: str) -> PrintTable:
        """This table in the order of the ``names`` columns (stable); itself when already in that order."""
        cols = [self._cols[name] for name in names]
        at = self._at

        def key(k: int) -> tuple:
            j = at(k)
            return tuple(col[j] for col in cols)
        n = len(self)
        if all(key(k - 1) <= key(k) for k in range(1, n)):
            return self
        return self.take(sorted(range(n), key=key))

    def numbered(self, name: str = "seq") -> PrintTable:
        """Every row gets ``name`` = its position in this table (the store's ordinal), as an int column."""
        if name not in _INTS:
            raise ValueError(f"{name} is not an int column")
        base = self.span(0, len(self))
        base._cols[name] = array("q", range(len(base)))
        reshaped = [tuple(entry for entry in shape if entry[0] != name) + ((name, _INT, None),) for shape in base._shapes]
        base._shapes, base._codes = reshaped, {}
        remap = array("I", (base._intern(shape) for shape in reshaped))
        base._code = array("I", (remap[c] for c in base._code))
        return base

    # -- the store's blob ---------------------------------------------------------------------------------------
    def pack(self) -> bytes:
        base = self if self._rows is None else self.span(0, len(self))
        return pack_columns(dict(base._cols, code=base._code),
                            dict(shapes=[[list(entry) for entry in shape] for shape in base._shapes]))

    @classmethod
    def unpack(cls, blob: bytes) -> PrintTable:
        columns, extra = unpack_columns(blob)
        out = cls()
        for name in (*FLOAT_COLUMNS, *INT_COLUMNS):
            out._cols[name] = columns[name]
        out._code = columns["code"]
        out._shapes = [tuple((key, kind, value) for key, kind, value in shape) for shape in extra["shapes"]]
        out._codes = {shape: i for i, shape in enumerate(out._shapes)}
        if any(len(col) != len(out._code) for col in out._cols.values()):
            raise ValueError("a packed print table's columns differ in length")
        return out


def pack_columns(columns: dict[str, array], extra: dict) -> bytes:
    """``columns`` and ``extra`` as one blob: a 4-byte header length, a JSON header naming each column's type
    code, length and the writer's byte order, then the columns' bytes in header order."""
    header = dict(schema_version=PACK_SCHEMA_VERSION, byteorder=sys.byteorder,
                  columns=[[name, col.typecode, len(col)] for name, col in columns.items()], extra=extra)
    head = json.dumps(header, separators=(",", ":")).encode()
    return b"".join([struct.pack("<I", len(head)), head, *(col.tobytes() for col in columns.values())])


def unpack_columns(blob: bytes) -> tuple[dict[str, array], dict]:
    """``pack_columns`` undone; a blob of another schema version, or cut short, is refused."""
    (size,) = struct.unpack_from("<I", blob, 0)
    header = json.loads(bytes(blob[4:4 + size]))
    if header.get("schema_version") != PACK_SCHEMA_VERSION:
        raise ValueError(f"Unsupported packed columns version {header.get('schema_version')}")
    at, columns = 4 + size, {}
    view = memoryview(blob)
    for name, typecode, length in header["columns"]:
        col = array(typecode)
        nbytes = col.itemsize * length
        if at + nbytes > len(blob):
            raise ValueError(f"Packed column {name} is cut short")
        col.frombytes(view[at:at + nbytes])
        if header["byteorder"] != sys.byteorder:
            col.byteswap()
        columns[name] = col
        at += nbytes
    return columns, header["extra"]

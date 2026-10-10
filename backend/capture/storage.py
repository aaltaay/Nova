"""Capture storage location; never falls back into the checkout.

Owns the capture root and the one way to name a Session Record's folder inside it
(``session_path``): every reader that takes a date and symbol from a request builds
the folder here, so a crafted name is refused in one place.
"""
import os
import re
from pathlib import Path

from capture.constants_capture import CAPTURE_DATE_RE, CAPTURE_REFUSED_ECHO_CHARS, CAPTURE_SYMBOL_RE

_DATE = re.compile(CAPTURE_DATE_RE, re.ASCII)
_SYMBOL = re.compile(CAPTURE_SYMBOL_RE, re.ASCII)


def capture_root() -> Path:
    from capture.constants_capture import DEFAULT_SIM_CAPTURE_ROOT_WIN

    override = (os.environ.get("NOVA_SIM_CAPTURE_DIR") or "").strip()
    preferred = Path(DEFAULT_SIM_CAPTURE_ROOT_WIN)
    if override:
        root = Path(override)
    elif preferred.drive and Path(preferred.drive + "\\").exists():
        root = preferred
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Nova" / "sim_capture"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Nova" / "sim_capture"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_path(date: str, symbol: str, *, root: Path | str | None = None) -> Path:
    """The folder of one Session Record, ``<root>/<date>/<SYMBOL>``; ``ValueError`` says why there is none.

    ``date`` and ``symbol`` come from requests, so a date that is not YYYY-MM-DD, a symbol
    that is not a ticker, or a folder that would land outside the capture root (``..``,
    an absolute path, a drive letter, a ``\\\\host\\share`` path) is refused before anything
    touches the disk. The folder is not required to exist. The symbol is upper-cased, as
    the recorder writes it; the layout on disk is unchanged.
    """
    day = str(date if date is not None else "")
    sym = str(symbol if symbol is not None else "").upper()
    if not _DATE.fullmatch(day):
        raise ValueError(f"A Session Record's date is YYYY-MM-DD, not {day[:CAPTURE_REFUSED_ECHO_CHARS]!r}")
    if not _SYMBOL.fullmatch(sym):
        raise ValueError("A Session Record's symbol is a ticker such as AAPL or BRK.B, "
                         f"not {sym[:CAPTURE_REFUSED_ECHO_CHARS]!r}")
    # The pattern checks above already rule out every separator; this lexical check is
    # what keeps the folder inside the root whatever the patterns allow. ``normpath``,
    # not ``realpath``: a junction the operator made inside the capture root stays usable.
    base = os.path.normpath(str(root if root is not None else capture_root()))
    folder = os.path.normpath(os.path.join(base, day, sym))
    if not folder.startswith(base if base.endswith(os.sep) else base + os.sep):
        raise ValueError(f"{day} {sym} is not inside the capture folder")
    return Path(folder)

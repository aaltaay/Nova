"""Make desk text safe for a public page -- pure.

Operator decision, 2026-09-24: "I really don't want any personal information about my computer,
but I need enough debugging points ... I don't want any security issues because this is real
money." Everything the desk posts -- the dump, and the title and description the operator types
-- passes through one ``Scrubber``. It removes, in this order:

- every secret value the backend holds, and token-shaped strings (``ghp_``, ``sk-``, AWS keys, JWTs);
- IBKR account ids (``U1234567``, ``DU1234567``);
- money figures: balances, buying power, P&L (by name), and dollar amounts of $1,000 or more
  (share prices stay -- a fill at $4.13 is a debugging fact);
- file paths: the repo root becomes ``<repo>``, the data drive ``<data>``, the home folder
  ``<home>``, any other path ``<path>``;
- the Windows user name, the machine name, e-mail addresses and IP addresses (loopback stays).

``value`` walks a JSON-like structure, dropping keys that name paths, files or environment
keys outright. The count of replacements is kept so the answer can say how much was removed.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from constants_issue_report import ISSUE_REPORT_REDACTED, ISSUE_REPORT_SECRET_MIN_LEN

_TOKENS = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}"
    r"|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,})"
)
_ACCOUNT_ID = re.compile(r"\b(?:DU|U)\d{6,9}\b")
_MONEY_NAMED = re.compile(
    r"(?i)\b(net[ _]?liq(?:uidation)?|buying[ _]?power|available[ _]?funds|excess[ _]?liquidity"
    r"|total[ _]?cash[ _]?value|cash|equity|gross[ _]?position[ _]?value|(?:day|realized|unrealized)[ _]?p&?n?l"
    r"|realized[ _]?today|starting[ _]?cash)\b(\W{0,4}?)(-?\$?\d[\d,]*(?:\.\d+)?)"
)
_MONEY_BIG = re.compile(r"-?\$\s?(?:\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d+)?")
# A drive path (either slash), a UNC path, or a file:/// URL of one; stops at quotes, spaces and brackets.
_WIN_PATH = re.compile(r"(?:file:/{2,3})?(?:\b[A-Za-z]:[\\/]|\\\\[\w.$-]+\\)[^\s\"'<>|,;()\[\]{}]*")
_POSIX_HOME = re.compile(r"/(?:home|Users)/[^\s/\"']+[^\s\"'<>|,;()\[\]{}]*")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_KEEP_IPS = {"127.0.0.1", "0.0.0.0"}
# Evidence keys whose values are paths, file lists or environment key names: dropped, not scrubbed.
_DROP_KEY = re.compile(r"(?i)(path|file|dir$|dirs$|root|executable|cwd|argv|^keys$|^env|folder|git_common|moved_from"
                       r"|^real$|label|hostname|user)")


def _norm(path: str) -> str:
    return path.replace("/", "\\").rstrip("\\").lower()


class Scrubber:
    """One pass over desk text for a public page; ``count`` says how many things it removed."""

    def __init__(self, *, secrets: Iterable[str] = (), roots: Sequence[tuple[str, str]] = (),
                 user: str | None = None, host: str | None = None) -> None:
        # An account id is the pattern's to replace whole: as a plain secret, U7654321 would leave the
        # "D" of DU7654321 behind.
        self._secrets = sorted({s for s in secrets if s and len(s) >= ISSUE_REPORT_SECRET_MIN_LEN
                                and not _ACCOUNT_ID.fullmatch(s)}, key=len, reverse=True)
        # Longest root first, so the repo (inside the home folder) wins over the home folder.
        self._roots = sorted(((_norm(p), label) for p, label in roots if p), key=lambda r: len(r[0]), reverse=True)
        # One label per pattern, from the same names and the same filter. ``text`` zips them strictly, so
        # the two drifting apart raises instead of skipping a name.
        self._names = [re.compile(rf"(?i)(?<![\w-]){re.escape(n)}(?![\w-])") for n in (user, host) if n and len(n) >= 3]
        self._name_labels = [label for n, label in ((user, "<user>"), (host, "<host>")) if n and len(n) >= 3]
        self.count = 0

    def _sub(self, pattern: re.Pattern[str], repl: Any, text: str) -> str:
        text, n = pattern.subn(repl, text)
        self.count += n
        return text

    def _path(self, match: re.Match[str]) -> str:
        raw = match.group(0)
        bare = re.sub(r"^file:/{2,3}", "", raw)
        low = _norm(bare)
        for root, label in self._roots:
            if low == root or low.startswith(root + "\\"):
                rest = bare[len(root):].replace("/", "\\")
                return label + rest
        return "<path>"

    def text(self, value: str) -> str:
        text = str(value)
        for secret in self._secrets:
            hits = text.count(secret)
            if hits:
                self.count += hits
                text = text.replace(secret, ISSUE_REPORT_REDACTED)
        text = self._sub(_TOKENS, ISSUE_REPORT_REDACTED, text)
        text = self._sub(_ACCOUNT_ID, "<account>", text)
        text = self._sub(_MONEY_NAMED, lambda m: f"{m.group(1)}{m.group(2)}<amount>", text)
        text = self._sub(_MONEY_BIG, "$<amount>", text)
        text = self._sub(_WIN_PATH, self._path, text)
        text = self._sub(_POSIX_HOME, "<path>", text)
        text = self._sub(_EMAIL, "<email>", text)
        text = self._sub(_IPV4, lambda m: m.group(0) if m.group(0) in _KEEP_IPS else "<ip>", text)
        for pattern, label in zip(self._names, self._name_labels, strict=True):
            text = self._sub(pattern, label, text)
        return text

    def value(self, obj: Any) -> Any:
        """A JSON-like structure with path / file / env-key fields dropped and every string scrubbed."""
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            out = {}
            for key, item in obj.items():
                if _DROP_KEY.search(str(key)):
                    self.count += 1
                    continue
                out[key] = self.value(item)
            return out
        if isinstance(obj, (list, tuple)):
            return [self.value(item) for item in obj]
        return obj

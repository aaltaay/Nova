"""Silent-failure heuristics (AGENTS.md §6.3): never swallow an exception silently.

Everywhere, a silent ``except`` / empty ``catch`` is an advisory finding. On the
**money path** -- the code that places, sizes or reports orders, positions and
the account -- it is a ``*_money`` finding that fails CI, because a desk that
swallows an order-row or account read is lying about its own state.

A site that is silent on purpose (a timeout that is the normal end of a wait,
an idempotent ``list.remove``, a parse that falls through to the next format)
says so where the next reader looks::

    except asyncio.TimeoutError:  # maintainer: allow-swallow the timeout ends the wait
        pass

The reason sits on the ``except`` / ``catch`` line, the line before it or the
body line. File-wide allowlists never apply on the money path.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

MONEY_PATH_PREFIXES = (
    "backend/execution/",    # the one order door (ADR 007)
    "backend/ibkr/",         # the broker, the account, the feed
    "backend/practice/",     # Paper / Sim ledger and fills (ADR 019, 020)
    "backend/sim/",          # the desk venue that decides where an order goes
    "backend/kill_switch/",  # the latch every place checks (ADR 025)
    "backend/bot/",          # the bot's own entries and exits (ADR 016, 027)
    "frontend/src/ibkr/",    # the ticket, orders and positions on screen
)

ALLOW_SWALLOW_RE = re.compile(r"maintainer:\s*allow-swallow\b[ \t:\-–—]*(?P<reason>[^\n]*)")
ALLOW_SWALLOW_MIN_REASON = 15

# `except <anything>:` then `pass` / `...` on the same line or the next one,
# with comments allowed on the header and between. A comment on the except
# line and a dotted exception name both used to hide a site from this check.
_EXCEPT_HEAD = r"^[ \t]*except\b[^\n:]*:"
_BODY = r"[ \t]+(?:pass|\.\.\.)[ \t]*(?:#[^\n]*)?$"
SWALLOW_PY = re.compile(
    _EXCEPT_HEAD + r"[ \t]*(?:pass|\.\.\.)[ \t]*(?:#[^\n]*)?$"
    r"|" + _EXCEPT_HEAD + r"[ \t]*(?:#[^\n]*)?\n(?:[ \t]*#[^\n]*\n)*" + _BODY,
    re.MULTILINE,
)
BARE_EXCEPT_PY = re.compile(r"^[ \t]*except\s*:\s*", re.MULTILINE)
EMPTY_CATCH_JS = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE)
# Promise .catch(() => {}) / .catch(() => {/* silent */})
EMPTY_CATCH_PROMISE_JS = re.compile(
    r"\.catch\(\s*\([^)]*\)\s*=>\s*\{\s*(?:/\*[^*]*\*/\s*)?\}\s*\)",
    re.MULTILINE,
)
# except …: return [] / {}  (failure disguised as empty market / empty state)
EXCEPT_RETURN_EMPTY_PY = re.compile(
    r"^[ \t]*except\b[^\n]*:\s*(?:#.*)?\n"
    r"(?:[ \t]+(?:logger\.[a-z_]+\([^\n]*\)|#[^\n]*)\n)*"
    r"[ \t]+return\s+(\[\s*\]|\{\s*\})\s*(?:#.*)?$",
    re.MULTILINE,
)

# Off the money path only (bucket B, fail-loud remainder plan): files whose
# empty-on-error is deliberate and already logged. See docs/agent-operations.md
# "Swallow heuristic policy". A money-path file never belongs here -- mark the
# site instead.
EXCEPT_RETURN_EMPTY_ALLOWLIST = {
    "backend/cache.py",  # corrupt disk cache -> empty, already logged
    "backend/alerts/channels_store.py",  # corrupt channels config -> empty, already logged
    "backend/journal/tags.py",  # bad tag JSON -> no tags (non-trading, cosmetic)
    "backend/scanner.py",  # Alpaca snapshot/news chunk failures — already loud-logged degrades
    "backend/capture/manifest_io.py",  # corrupt capture manifest -> empty, already warn-logged
}
SWALLOWED_EXCEPTION_ALLOWLIST: set[str] = set()

_PY_PATTERNS = (
    ("swallowed_exception", SWALLOW_PY, "except …: pass/… swallow"),
    ("except_return_empty", EXCEPT_RETURN_EMPTY_PY, None),
)
_JS_PATTERNS = (
    ("empty_catch", EMPTY_CATCH_JS, "empty catch { }"),
    ("empty_promise_catch", EMPTY_CATCH_PROMISE_JS, "empty .catch(() => {})"),
)


def is_money_path(rel: str) -> bool:
    return rel.replace("\\", "/").startswith(MONEY_PATH_PREFIXES)


def _marker_reason(text: str, start: int, end: int) -> str | None:
    """The allow-swallow reason in the site's window, None when unmarked."""
    line_start = text.rfind("\n", 0, start) + 1
    prev_start = text.rfind("\n", 0, max(0, line_start - 1)) + 1
    line_end = text.find("\n", end)
    window = text[prev_start: len(text) if line_end < 0 else line_end]
    match = ALLOW_SWALLOW_RE.search(window)
    if match is None:
        return None
    return match.group("reason").strip().rstrip("*/").strip()


def _site(kind, rel, detail, text, match, finding_cls, allowlist) -> object | None:
    money = is_money_path(rel)
    if not money and rel in allowlist:
        return None
    line = text.count("\n", 0, match.start()) + 1
    reason = _marker_reason(text, match.start(), match.end())
    if reason is not None:
        if len(reason) >= ALLOW_SWALLOW_MIN_REASON:
            return None
        return finding_cls(
            kind="allow_swallow_no_reason", path=rel, line=line,
            detail=(f"`maintainer: allow-swallow` needs a reason of at least "
                    f"{ALLOW_SWALLOW_MIN_REASON} characters"),
        )
    return finding_cls(kind=f"{kind}_money" if money else kind, path=rel, detail=detail, line=line)


def check_swallowed_errors(
    files: list[Path],
    rel_fn: Callable[[Path], str],
    finding_cls: type,
    exempt_py: Callable[[Path], bool],
) -> list:
    """Silent-failure findings. ``exempt_py`` skips tools/ and tests for Python."""
    findings = []
    for path in files:
        if path.suffix == ".css":
            continue
        rel = rel_fn(path).replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".py":
            if exempt_py(path):
                continue
            for kind, pattern, detail in _PY_PATTERNS:
                allowlist = (SWALLOWED_EXCEPTION_ALLOWLIST if kind == "swallowed_exception"
                             else EXCEPT_RETURN_EMPTY_ALLOWLIST)
                for match in pattern.finditer(text):
                    text_detail = detail or (
                        f"except …: return {match.group(1)} — failure may look like empty market"
                    )
                    found = _site(kind, rel, text_detail, text, match, finding_cls, allowlist)
                    if found is not None:
                        findings.append(found)
            for match in BARE_EXCEPT_PY.finditer(text):
                snippet = text[match.start(): match.start() + 40]
                if "pass" in snippet or "..." in snippet:
                    continue
                found = _site("bare_except", rel, "bare except:", text, match, finding_cls, set())
                if found is not None:
                    findings.append(found)
        elif path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            for kind, pattern, detail in _JS_PATTERNS:
                for match in pattern.finditer(text):
                    found = _site(kind, rel, detail, text, match, finding_cls, set())
                    if found is not None:
                        findings.append(found)
    return findings

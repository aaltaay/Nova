"""Ahead's import boundaries (ADR 061): a chart study the money path never reads, and that reads only its own
inputs' owners -- never the stock read, a broker, an order or a bot."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
# Every package an order, a fill, a position or a bot's decision goes through, and the scanner's setups.
MONEY_PATH = ("execution", "ibkr", "practice", "sim", "kill_switch", "bot", "market_view", "short_sale",
              "loss_limit", "setup_scanner")
# What backend/ahead/ may import outside the standard library and itself.
ALLOWED = {
    "constants_ahead", "http_pool", "requests", "fastapi", "scanner_wire",
    "sensors.feeds", "stock_read.replay_read", "stock_read.indicators",
    "sim.mode", "sim.history_playback", "sim.capture_player",
    "strategy.symbol_pillars",
}


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


@pytest.mark.parametrize("package", MONEY_PATH)
def test_no_money_path_package_imports_ahead(package):
    offenders = [str(p.relative_to(BACKEND)) for p in (BACKEND / package).rglob("*.py")
                 if any(name == "ahead" or name.startswith("ahead.") for name in _imports(p))]
    assert offenders == []


def _allowed(name: str) -> bool:
    root = name.split(".")[0]
    if root in sys.stdlib_module_names or root == "ahead" or root == "__future__":
        return True
    return any(name == ok or name.startswith(ok + ".") for ok in ALLOWED)


def _units(path: Path) -> set[str]:
    """What a file imports, judged whole: ``from X import a`` is ``X`` when ``X`` is allowed, else ``X.a``."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if _allowed(node.module):
                out.add(node.module)
            else:
                out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def test_ahead_imports_only_its_allow_list():
    seen = {path.name: sorted(n for n in _units(path) if not _allowed(n))
            for path in sorted((BACKEND / "ahead").glob("*.py"))}
    assert {k: v for k, v in seen.items() if v} == {}


def test_ahead_never_reads_the_stock_read_itself():
    for path in (BACKEND / "ahead").glob("*.py"):
        names = _imports(path)
        assert not any(n.startswith(("stock_read.routes", "stock_read.gather", "stock_read.read")) for n in names), path

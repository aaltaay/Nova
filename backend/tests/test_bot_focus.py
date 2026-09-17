"""Bot focus shares the max-3 live L2 cap."""
from __future__ import annotations

import pytest

from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.focus import add_focus, set_focus, snapshot, sync_trader_live
from constants import IBKR_MAX_DEPTH_SYMBOLS
from constants_bot import BOT_REASON_L0_DARK


def test_l0_cannot_set_focus():
    with pytest.raises(BotError) as exc:
        set_focus(["AAPL"])
    assert exc.value.reason == BOT_REASON_L0_DARK


def test_focus_and_trader_live_cap():
    apply_patch({"level": 1}, desk=True)
    out = set_focus(["aapl", "AAPL", "msft", "nvda"])
    assert out["focus"] == ["AAPL", "MSFT", "NVDA"]
    add_focus("tsla")
    assert "TSLA" in snapshot()["focus"]
    live = sync_trader_live(["AAA", "BBB", "CCC", "DDD"])
    assert live["trader_live"] == ["AAA", "BBB", "CCC"]
    assert live["live_cap"] == IBKR_MAX_DEPTH_SYMBOLS == 3
    assert len(live["trader_live"]) <= 3

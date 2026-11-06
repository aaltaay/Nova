"""The request bodies of ``/api/agent/trader`` (ADR 068), apart from the routes that read them."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent_trader.constants_agent_trader import (
    AGENT_POP_PCT_MAX,
    AGENT_POP_PCT_MIN,
)


class WatchBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


class OrderBody(BaseModel):
    kind: Literal["limit", "break"]
    symbol: str = Field(min_length=1, max_length=10)
    qty: float = Field(gt=0)
    entry: float | None = Field(default=None, gt=0)      # a limit's price
    trigger: float | None = Field(default=None, gt=0)    # a break: a print at or above this ...
    top: float | None = Field(default=None, gt=0)        # ... sends a buy up to this price
    stop: float = Field(gt=0)
    target: float = Field(gt=0)
    target2: float | None = Field(default=None, gt=0)
    target1_qty: float | None = Field(default=None, gt=0)
    minutes: float | None = Field(default=None, gt=0)    # a break's life
    confirm: ConfirmBody | None = None                   # a break sends only while buyers lead (reflexes.confirmed)
    exit: Literal["pop"] | None = None                   # half at the first pop, then the stop to entry (decision 13)
    pop_pct: float | None = Field(default=None, ge=AGENT_POP_PCT_MIN, le=AGENT_POP_PCT_MAX)
    why: str = Field(min_length=1, max_length=400)       # one line for the desk


class ConfirmBody(BaseModel):
    seconds: float = Field(gt=0)
    shares: float = Field(gt=0)
    ratio: float = Field(gt=0)


class ReflexBody(BaseModel):
    kind: Literal["bid_pulled", "ask_wall", "sellers", "last_below"]
    action: Literal["sell_all", "cancel_buy"]
    price: float | None = Field(default=None, gt=0)
    shares: float | None = Field(default=None, gt=0)
    seconds: float | None = Field(default=None, gt=0)
    ratio: float | None = Field(default=None, gt=0)
    minutes: float | None = Field(default=None, gt=0)
    why: str = Field(min_length=1, max_length=400)


class StopBody(BaseModel):
    order_id: int
    stop: float = Field(gt=0)


class CloseBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)


class NoteBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)


class TakeBackBody(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)

"""How the Cryptos page reads a crypto headline (ADR 040): a rules read, no model, the same idea as ADR 024.

A headline is one of:
- ``catalyst`` -- something happened that can move the coin: ETF approvals and inflows, upgrades, listings,
  partnerships and adoption, a treasury buying, a case won or settled;
- ``negative`` -- hacks and exploits, delistings, lawsuits and charges, outflows, halted withdrawals, token
  unlocks (new supply), bans;
- ``noise`` -- the price talking about itself: "why is X up", predictions, top-N lists, recaps, levels crossed,
  whale watching, liquidation tallies; and any roundup naming more than ``CRYPTO_NEWS_ROUNDUP_TICKERS`` coins;
- ``news`` -- anything else about the coin.
A "why is it up" headline, a level crossed or a whale sighting that also names a cause ("Why Solana is rising:
its upgrade went live") is read by the cause; a prediction, a top-N list or a recap stays noise whatever it names.
Rules version ``CRYPTO_NEWS_RULES_VERSION``.
"""
from __future__ import annotations

import re
from typing import Iterable

from constants_crypto import CRYPTO_NEWS_ROUNDUP_TICKERS

KIND_CATALYST = "catalyst"
KIND_NEGATIVE = "negative"
KIND_NOISE = "noise"
KIND_NEWS = "news"
KINDS = (KIND_CATALYST, KIND_NEGATIVE, KIND_NOISE, KIND_NEWS)


def _rx(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


_NEGATIVE = _rx(
    r"\b(?:hack(?:ed|s|ers?)?|exploit(?:ed|s)?|drained|stolen|theft)\b",
    r"\bsecurity\s+breach\b",
    r"\bdelist(?:s|ed|ing)?\b",
    r"\b(?:sues?|sued|lawsuit|charged|indict(?:ed|ment)?|fraud|subpoena(?:ed)?)\b",
    r"\b(?:SEC|CFTC|DOJ|prosecutors?|regulators?)\b.{0,40}\b(?:charges?|probe[sd]?|investigat\w*)\b",
    r"\boutflows?\b",
    r"\b(?:halts?|pauses?|suspends?|freezes?)\s+withdrawals?\b",
    r"\bwithdrawals?\s+(?:halted|paused|suspended|frozen)\b",
    r"\b(?:bankrupt(?:cy)?|insolven(?:t|cy))\b",
    r"\btoken\s+unlocks?\b",
    r"\bunlock(?:s|ed|ing)?\b.{0,40}\b(?:tokens?|supply)\b",
    r"\b(?:tokens?|supply)\b.{0,40}\bunlock(?:s|ed|ing)?\b",
    r"\b(?:bans?|banned|crackdown)\b",
)
_CATALYST = _rx(
    r"\bETFs?\b.{0,60}\b(?:approv\w*|launch\w*|inflows?|debut\w*|green[- ]?light\w*)\b",
    r"\b(?:approv\w*|launch\w*|green[- ]?light\w*)\b.{0,60}\bETFs?\b",
    r"\binflows?\b",
    r"\b(?:upgrade|mainnet|hard\s+fork|activation|goes\s+live|went\s+live)\b",
    r"\b(?:partner(?:s|ship|ships)?|integrat(?:es|ed|ion)|adopt(?:s|ed|ion))\b",
    r"\b(?:lists?|listing|listed)\s+on\b",
    r"\b(?:coinbase|binance|kraken|robinhood|okx|bybit|upbit|bithumb|gemini)\b.{0,30}"
    r"\b(?:lists?|listing|adds?|will\s+list|to\s+list)\b",
    r"\b(?:treasury|reserve)\b.{0,60}\b(?:buys?|bought|adds?|added|purchas\w*|acquir\w*)\b",
    r"\b(?:buys?|bought|adds?|added|purchas\w*|acquir\w*)\b.{0,40}\b(?:bitcoin|btc|ether|eth|sol|xrp)\b",
    r"\b(?:wins?|won)\b.{0,40}\b(?:case|lawsuit|ruling|appeal)\b",
    r"\b(?:dismiss(?:es|ed)?|drops?|dropped)\b.{0,20}\b(?:case|lawsuit|charges)\b",
    r"\bsettle(?:s|d|ment)?\b.{0,30}\b(?:SEC|CFTC|DOJ|lawsuit|case|charges|regulators?)\b",
    r"\b(?:SEC|CFTC|DOJ|regulators?)\b.{0,30}\bsettle(?:s|d|ment)?\b",
)
# Always noise: the piece is about the price or a list, whatever cause it mentions.
_NOISE_ALWAYS = _rx(
    r"\bprice\s+(?:prediction|analysis|forecast|outlook)s?\b",
    r"\b(?:top|best)\s+\d+\b",
    r"\b(?:should\s+you|is\s+it\s+time\s+to|what'?s\s+next\s+for)\b",
    r"\bcould\b.{0,40}\breach\b",
    r"\bwill\b.{0,40}\bhit\b",
    r"\b(?:technical|chart)\s+analysis\b",
    r"\b(?:market|daily|weekly)\s+(?:update|wrap|recap)\b",
    r"\bcrypto\s+market\s+today\b",
    r"\b(?:movers|biggest\s+(?:gainers|losers))\b",
)
# Noise unless the title also names a cause: "why is it up", levels crossed, whales, liquidation tallies.
_NOISE_UNLESS_CAUSE = _rx(
    r"\bwhy\s+(?:is|are|did|does|has)\b",
    r"\bhere'?s\s+why\b",
    r"\b(?:record|all[- ]time|new)\s+highs?\b",
    r"\b(?:hits?|tops?|crosses|breaks|breaches|reclaims?|settles\s+(?:above|below)|falls?\s+below|drops?\s+below|slips?\s+below)\s+\$",
    r"\bwhales?\b",
    r"\bliquidat\w*\b",
)


def classify_headline(title: str | None, summary: str | None = None, n_tickers: int | None = None) -> str:
    """One headline's kind (``KINDS``)."""
    text = " ".join(t for t in ((title or "").strip(), (summary or "").strip()) if t)
    if not text:
        return KIND_NEWS
    if n_tickers is not None and n_tickers > CRYPTO_NEWS_ROUNDUP_TICKERS:
        return KIND_NOISE
    title_only = (title or "").strip()
    if _NOISE_ALWAYS.search(title_only):
        return KIND_NOISE
    # The cause is read from the title first: a summary is where "why is it moving" pieces list every rumour.
    if _NEGATIVE.search(title_only):
        return KIND_NEGATIVE
    if _CATALYST.search(title_only):
        return KIND_CATALYST
    if _NOISE_UNLESS_CAUSE.search(title_only):
        return KIND_NOISE
    if _NEGATIVE.search(text):
        return KIND_NEGATIVE
    if _CATALYST.search(text):
        return KIND_CATALYST
    return KIND_NEWS


_RANK = {KIND_CATALYST: 0, KIND_NEGATIVE: 0, KIND_NEWS: 1, KIND_NOISE: 2}


def best_item(items: Iterable[dict]) -> dict | None:
    """The headline that best answers "why is it moving": a catalyst or a negative first, then other news,
    then noise; the newest within a rank."""
    ranked = sorted(items, key=lambda it: (_RANK.get(str(it.get("kind")), 3), -(it.get("published_ts") or 0.0)))
    return ranked[0] if ranked else None

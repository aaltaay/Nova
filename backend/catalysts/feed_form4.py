"""The live catalyst feed's Form 4 source, ``edgar_form4`` (#517, ADR 024).

EDGAR's latest ownership filings of type 4 (``owner=only``), read as they are filed. Each filing is
listed once per party -- the reporting owner and the issuer -- and only the issuer's entry is taken:
its CIK names the ticker (SEC's ``company_tickers.json``, the feed's own map). A listed issuer's
filing is fetched once, as its full submission text (one request, paced by the feed's SEC gap), and
recorded only when it holds an open-market purchase by an officer or a director
(``catalysts/form4.py``); every other Form 4 is read and let go. Amendments (4/A) are not read.

**Its own span.** Form 4s come in the hundreds after the close; a burst breaks this span, never the
8-K / 6-K one. A poll pages back to the span's end (at most ``CATALYST_FEED_FORM4_MAX_PAGES``) and is
complete only when every listed issuer's filing since then has been read. A filing that cannot be
fetched is retried on the next polls; after ``CATALYST_FEED_FORM4_MAX_ATTEMPTS`` -- or at once when
the document cannot be parsed -- it is a **known miss**: the span breaks there and the next one opens
after it, so coverage is never claimed across a filing nobody read.

Owner: this module (in memory: retry counts and the floor after a miss). Invalidation: a filing's
retry count goes when it is read, given up or no longer listed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Mapping

from catalysts import feed_sources, form4
from constants_catalysts import (
    CATALYST_FEED_FORM4_ATOM,
    CATALYST_FEED_FORM4_MAX_ATTEMPTS,
    CATALYST_FEED_FORM4_MAX_PAGES,
    CATALYST_FEED_FORM4_MAX_READS,
    CATALYST_FEED_FORM4_PAGE,
    CATALYST_FEED_FORM4_SUBMISSION,
    CATALYST_INSIDER_BUY_FORM,
)

logger = logging.getLogger(__name__)
ISSUER_ROLE = "Issuer"
SOURCE = "edgar"              # the items are SEC filings like any other; the coverage span is edgar_form4's
PUBLISHER = "SEC EDGAR"


@dataclass
class Form4Poll:
    items: list[dict] = field(default_factory=list)          # purchases to record
    settled: dict[str, float] = field(default_factory=dict)  # item id -> accepted time: read, no purchase
    oldest: float | None = None       # every listed filing after this was read (the span's start candidate)
    complete: bool = True             # nothing listed since ``since`` is left unread
    missed_ts: float | None = None    # the newest filing given up this poll: the span breaks there


class Form4Reader:
    def __init__(self, sec_get: Callable[[str], bytes]):
        self._get = sec_get
        self._attempts: dict[str, int] = {}
        self._floor: float | None = None   # a known miss: no span may open before it

    def poll(self, *, since: float | None, tickers: Mapping[str, list[str]],
             seen: Callable[[str], bool]) -> Form4Poll:
        """Read the filings listed since ``since`` (the span's end; None: one page) that ``seen`` has not."""
        out = Form4Poll()
        if not tickers:
            out.complete = False    # no CIK -> ticker map: nothing can be read, so nothing is covered
            return out
        listed = self._list(since, out)
        if not listed:
            out.complete = False    # EDGAR always lists recent Form 4s: an empty page proves nothing
            return out
        fresh = {f["acc"]: f for f in listed if f["role"] == ISSUER_ROLE and f["form"] == CATALYST_INSIDER_BUY_FORM
                 and tickers.get(f["cik"]) and not seen(f"{SOURCE}:{f['acc']}")}
        self._attempts = {acc: n for acc, n in self._attempts.items() if acc in fresh}
        for n, f in enumerate(sorted(fresh.values(), key=lambda f: f["accepted_ts"])):
            if n >= CATALYST_FEED_FORM4_MAX_READS:
                out.complete = False    # the rest are read on the next poll
                break
            self._read(f, list(tickers[f["cik"]]), out)
        if self._floor is not None and out.oldest is not None:
            out.oldest = max(out.oldest, self._floor)
        if out.complete:
            self._floor = None          # the span this poll opens or extends starts after the miss
        return out

    def _list(self, since: float | None, out: Form4Poll) -> list[dict]:
        listed: list[dict] = []
        for page in range(CATALYST_FEED_FORM4_MAX_PAGES):
            url = CATALYST_FEED_FORM4_ATOM.format(start=page * CATALYST_FEED_FORM4_PAGE, count=CATALYST_FEED_FORM4_PAGE)
            filings = feed_sources.parse_edgar_atom(self._get(url))
            if not filings:
                break
            listed += filings
            out.oldest = min(f["accepted_ts"] for f in listed)
            if since is None or out.oldest <= since:
                break
        return listed

    def _read(self, f: dict, tickers: list[str], out: Form4Poll) -> None:
        acc, ts, item_id = f["acc"], f["accepted_ts"], f"{SOURCE}:{f['acc']}"
        url = CATALYST_FEED_FORM4_SUBMISSION.format(cik=f["cik"], acc=acc.replace("-", ""), acc_dashed=acc)
        try:
            raw = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- retried next poll; given up (a stated miss) after the last try
            tries = self._attempts.get(acc, 0) + 1
            if tries < CATALYST_FEED_FORM4_MAX_ATTEMPTS:
                self._attempts[acc] = tries
                out.complete = False
                logger.info("catalyst feed: Form 4 %s unread (try %d): %s", acc, tries, exc)
                return
            logger.warning("catalyst feed: Form 4 %s given up after %d tries: %s", acc, tries, exc)
            self._miss(acc, ts, item_id, out)
            return
        self._attempts.pop(acc, None)
        filing = form4.parse(raw)
        if filing is None:
            logger.warning("catalyst feed: Form 4 %s has no readable ownership document", acc)
            self._miss(acc, ts, item_id, out)
            return
        buy = form4.insider_purchase(filing)
        if buy is None:
            out.settled[item_id] = ts
            return
        out.items.append({"item_id": item_id, "source": SOURCE, "published_ts": ts, "title": form4.title(buy),
                          "summary": form4.summary(buy), "url": f["url"], "publisher": PUBLISHER,
                          "form": CATALYST_INSIDER_BUY_FORM, "sec_items": form4.stamp(buy.total_usd),
                          "tickers": tickers, "n_tickers": 1})

    def _miss(self, acc: str, ts: float, item_id: str, out: Form4Poll) -> None:
        self._attempts.pop(acc, None)
        out.settled[item_id] = ts
        out.missed_ts = ts if out.missed_ts is None else max(out.missed_ts, ts)
        self._floor = ts if self._floor is None else max(self._floor, ts)

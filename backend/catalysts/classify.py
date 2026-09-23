"""Is this a real catalyst? One pure classifier for the history and the live desk (ADR 024).

``classify_item`` labels one article or filing:

  noise     movers lists and "why is it moving" pieces, law-firm adverts, opinion mills,
            roundups naming many tickers -- never the company's own news
  routine   company items that are not catalysts: an earnings date, a conference, an officer
            change, a periodic report
  negative  dilution (offerings, warrants, ATM programs, shelf registrations) and delisting /
            reverse-split news
  catalyst  company-specific positive news, ``strong`` or ``weak`` by class

``verdict`` answers for one symbol-day from the items published after the window opened and at
or before the cutoff -- never later, so a backtest never learns a catalyst from hindsight. A
verdict says ``none_found`` only when a source actually answered; ``not_checked`` otherwise.

Pure: no I/O, no clock.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from constants_catalysts import (
    CATALYST_ANALYST_RE,
    CATALYST_CLINICAL_STRONG_RE,
    CATALYST_CLINICAL_WEAK_RE,
    CATALYST_CONTRACT_STRONG_RE,
    CATALYST_CONTRACT_WEAK_RE,
    CATALYST_DELISTING_RE,
    CATALYST_EARNINGS_STRONG_RE,
    CATALYST_EARNINGS_WEAK_RE,
    CATALYST_FDA_STRONG_RE,
    CATALYST_FDA_WEAK_RE,
    CATALYST_FINANCE_POSITIVE_RE,
    CATALYST_FLUFF_RE,
    CATALYST_HALT_RE,
    CATALYST_KIND_CATALYST,
    CATALYST_KIND_NEGATIVE,
    CATALYST_KIND_NOISE,
    CATALYST_KIND_ROUTINE,
    CATALYST_LAW_FIRM_RE,
    CATALYST_MAX_TICKERS,
    CATALYST_MERGER_STRONG_RE,
    CATALYST_MERGER_WEAK_RE,
    CATALYST_MOVERS_RE,
    CATALYST_OFFERING_ENDED_RE,
    CATALYST_OFFERING_RE,
    CATALYST_OPINION_PUBLISHERS,
    CATALYST_OPINION_RE,
    CATALYST_PRODUCT_RE,
    CATALYST_REBRAND_RE,
    CATALYST_REGAINED_RE,
    CATALYST_ROUTINE_RE,
    CATALYST_RULES_VERSION,
    CATALYST_SEC_COVER_RE,
    CATALYST_SEC_FORM_CLASS,
    CATALYST_SEC_ITEM_FALLBACK,
    CATALYST_SOURCE_RANK,
    CATALYST_STRONG,
    CATALYST_SUMMARY_CHARS,
    CATALYST_THEME_RE,
    CATALYST_UNCLASSIFIED,
    CATALYST_VERDICT_CATALYST,
    CATALYST_VERDICT_NEGATIVE,
    CATALYST_VERDICT_NOISE,
    CATALYST_VERDICT_NONE,
    CATALYST_VERDICT_NOT_CHECKED,
    CATALYST_VERDICT_ROUTINE,
    CATALYST_WEAK,
)
from news.junk import is_junk_headline, is_movers_url


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_LAW, _MOVERS, _OPINION, _ROUTINE = _rx(CATALYST_LAW_FIRM_RE), _rx(CATALYST_MOVERS_RE), _rx(CATALYST_OPINION_RE), _rx(CATALYST_ROUTINE_RE)
_HALT, _ANALYST = _rx(CATALYST_HALT_RE), _rx(CATALYST_ANALYST_RE)
_REBRAND, _REGAINED, _THEME = _rx(CATALYST_REBRAND_RE), _rx(CATALYST_REGAINED_RE), _rx(CATALYST_THEME_RE)
_FLUFF, _SEC_COVER, _EARN_WEAK = _rx(CATALYST_FLUFF_RE), _rx(CATALYST_SEC_COVER_RE), _rx(CATALYST_EARNINGS_WEAK_RE)
_OFFER, _OFFER_ENDED, _DELIST = _rx(CATALYST_OFFERING_RE), _rx(CATALYST_OFFERING_ENDED_RE), _rx(CATALYST_DELISTING_RE)
# Categories that name no event: a movers-section article that lands on one of these stays a movers list.
_UNPLACED = frozenset({CATALYST_UNCLASSIFIED, "theme_pivot"})
# (category, strength, pattern), strongest first. The first match names the item.
_POSITIVE = (
    ("fda_regulatory", CATALYST_STRONG, _rx(CATALYST_FDA_STRONG_RE)),
    ("clinical_data", CATALYST_STRONG, _rx(CATALYST_CLINICAL_STRONG_RE)),
    ("merger_acquisition", CATALYST_STRONG, _rx(CATALYST_MERGER_STRONG_RE)),
    ("contract_partnership", CATALYST_STRONG, _rx(CATALYST_CONTRACT_STRONG_RE)),
    ("earnings_guidance", CATALYST_STRONG, _rx(CATALYST_EARNINGS_STRONG_RE)),
    ("fda_regulatory", CATALYST_WEAK, _rx(CATALYST_FDA_WEAK_RE)),
    ("clinical_data", CATALYST_WEAK, _rx(CATALYST_CLINICAL_WEAK_RE)),
    ("merger_acquisition", CATALYST_WEAK, _rx(CATALYST_MERGER_WEAK_RE)),
    ("contract_partnership", CATALYST_WEAK, _rx(CATALYST_CONTRACT_WEAK_RE)),
    ("earnings_guidance", CATALYST_WEAK, _rx(CATALYST_EARNINGS_WEAK_RE)),
    ("listing_financing", CATALYST_WEAK, _rx(CATALYST_FINANCE_POSITIVE_RE)),
    ("theme_pivot", CATALYST_WEAK, _rx(CATALYST_THEME_RE)),
    ("product_news", CATALYST_WEAK, _rx(CATALYST_PRODUCT_RE)),
)
_STRONG = tuple(entry for entry in _POSITIVE if entry[1] == CATALYST_STRONG)
_ROUTINE_ITEMS = frozenset({"5.02", "5.03", "5.05", "5.07", "5.08", "1.02", "2.03", "2.05", "4.01"})
_KIND_RANK = {CATALYST_KIND_CATALYST: 0, CATALYST_KIND_NEGATIVE: 1, CATALYST_KIND_ROUTINE: 2, CATALYST_KIND_NOISE: 3}


@dataclass(frozen=True)
class Label:
    kind: str
    category: str
    strength: str | None = None
    dilution: bool = False   # a catalyst announced together with a raise (merger + concurrent placement)


def classify_item(title: str | None, summary: str | None = None, *, source: str = "", publisher: str = "",
                  n_tickers: int | None = None, form: str | None = None, sec_items: str | None = None,
                  url: str = "") -> Label:
    """Label one article or filing. EDGAR items also read the opening of the filed release."""
    label = _classify(title, summary, source=source, publisher=publisher, n_tickers=n_tickers, form=form,
                      sec_items=sec_items)
    if source != "edgar" and is_movers_url(url) and label.kind != CATALYST_KIND_NOISE and not (
            label.kind in (CATALYST_KIND_CATALYST, CATALYST_KIND_NEGATIVE) and label.category not in _UNPLACED):
        # Benzinga's movers section is mostly lists, halt notices and commentary, but it also carries real
        # rewrites ("Surf Air Mobility Adds Second OperatorOS Customer"): its address alone no longer decides (v5).
        return Label(CATALYST_KIND_NOISE, "movers_list")
    return label


def _classify(title: str | None, summary: str | None, *, source: str, publisher: str, n_tickers: int | None,
              form: str | None, sec_items: str | None) -> Label:
    title = (title or "").strip()
    is_sec = source == "edgar"
    # An EDGAR title is "<form: items> | <release headline>"; without a release there is no headline,
    # only the Item text in the summary (never match the item names themselves, e.g. "reverse split").
    head = (title.split(" | ", 1)[1] if " | " in title else "") if is_sec else title
    if is_sec and _SEC_COVER.search(head):
        head = ""  # the extractor caught the form's cover page, not a release
    text = f"{head} {(summary or '')[:CATALYST_SUMMARY_CHARS]}" if is_sec else head
    if not is_sec:
        if _HALT.search(head):
            return Label(CATALYST_KIND_NOISE, "halt_notice")
        if _LAW.search(head):
            return Label(CATALYST_KIND_NOISE, "law_firm")
        if is_junk_headline(head) or _MOVERS.search(head):
            return Label(CATALYST_KIND_NOISE, "movers_list")
        if _OPINION.search(head):
            return Label(CATALYST_KIND_NOISE, "opinion")
        if n_tickers is not None and n_tickers > CATALYST_MAX_TICKERS:
            return Label(CATALYST_KIND_NOISE, "roundup")
    if is_sec and form in CATALYST_SEC_FORM_CLASS and not form.startswith(("8-K", "6-K")):
        kind, category, strength = CATALYST_SEC_FORM_CLASS[form]
        return Label(kind, category, strength)
    all_codes = {c.strip() for c in (sec_items or "").split(",") if c.strip()}
    codes = all_codes - {"9.01", "7.01", "8.01"}
    if is_sec and not head and codes and codes <= _ROUTINE_ITEMS:
        # An officer change or a vote with no release attached: its text ("employment agreement
        # with ...") must not read as a contract.
        return Label(CATALYST_KIND_ROUTINE, "corporate_routine")
    if is_sec and not head and "3.01" in codes:
        return Label(CATALYST_KIND_NEGATIVE, "delisting_split")  # the notice itself, whatever it quotes
    if not is_sec and _ANALYST.search(head):
        return Label(CATALYST_KIND_ROUTINE, "analyst_action")
    # A filed release's own headline says what it is; its body is read only when there is no headline
    # (an auditor's report or an officer's appointment quotes financing terms without raising money).
    deal_text = head if is_sec and head else text
    if _OFFER_ENDED.search(deal_text):
        return Label(CATALYST_KIND_CATALYST, "listing_financing", CATALYST_WEAK)
    raising = bool(_OFFER.search(deal_text))
    for category, strength, rx in _STRONG:
        if rx.search(text):  # a merger or an offtake announced with its financing is still the catalyst
            return Label(CATALYST_KIND_CATALYST, category, strength, dilution=raising)
    if raising:
        return Label(CATALYST_KIND_NEGATIVE, "offering_dilution")
    if _ROUTINE.search(head) or (_REBRAND.search(head) and not _THEME.search(head)):
        return Label(CATALYST_KIND_ROUTINE, "corporate_routine")
    if _REGAINED.search(head):
        return Label(CATALYST_KIND_CATALYST, "listing_financing", CATALYST_WEAK)
    if _DELIST.search(head):
        return Label(CATALYST_KIND_NEGATIVE, "delisting_split")
    if _FLUFF.search(head) and not _EARN_WEAK.search(head):
        return Label(CATALYST_KIND_ROUTINE, "corporate_routine")
    for category, strength, rx in _POSITIVE:
        if rx.search(text):
            return Label(CATALYST_KIND_CATALYST, category, strength)
    if not is_sec and (publisher or "").strip().lower() in CATALYST_OPINION_PUBLISHERS:
        return Label(CATALYST_KIND_NOISE, "opinion")
    if is_sec:
        if all_codes - {"9.01"} == {"7.01"}:
            return Label(CATALYST_KIND_ROUTINE, "presentation")  # Regulation FD alone: slides, not a release
        for code in ("2.01", "3.02", "3.01", "1.01", "2.02", "5.03", "5.02", "5.07"):
            if code in codes:
                kind, category, strength = CATALYST_SEC_ITEM_FALLBACK[code]
                return Label(kind, category, strength)
        if head:  # a filed release we could not place: the company's own news
            return Label(CATALYST_KIND_CATALYST, "company_news", CATALYST_WEAK)
        return Label(CATALYST_KIND_ROUTINE, "filing_other")
    return Label(CATALYST_KIND_CATALYST, "company_news", CATALYST_WEAK) if head else Label(CATALYST_KIND_NOISE, "empty")


def _rank(item: Mapping, label: Label) -> tuple:
    source = str(item.get("source") or "")
    return (_KIND_RANK[label.kind], 0 if label.strength == CATALYST_STRONG else 1,
            CATALYST_SOURCE_RANK.index(source) if source in CATALYST_SOURCE_RANK else len(CATALYST_SOURCE_RANK),
            float(item.get("published_ts") or 0.0))


def verdict(items: Iterable[Mapping], *, window_start: float, cutoff: float,
            sources_answered: Iterable[str] = ()) -> dict:
    """One symbol-day's answer from items published in (window_start, cutoff].

    ``items`` carry ``title, summary, source, publisher, n_tickers, form, sec_items, url,
    published_ts`` (missing keys are fine). ``sources_answered`` names the sources that looked
    for this ticker and day, found or not.
    """
    answered = sorted(set(sources_answered))
    seen = []
    for it in items:
        ts = float(it.get("published_ts") or 0.0)
        if not window_start < ts <= cutoff:
            continue
        label = classify_item(it.get("title"), it.get("summary"), source=str(it.get("source") or ""),
                              publisher=str(it.get("publisher") or ""), n_tickers=it.get("n_tickers"),
                              form=it.get("form"), sec_items=it.get("sec_items"), url=str(it.get("url") or ""))
        seen.append((it, label))
    out = {"rules_version": CATALYST_RULES_VERSION, "sources_answered": answered, "n_items": len(seen),
           "category": None, "strength": None, "title": None, "source": None, "published_ts": None,
           "url": None, "negative_too": any(lb.kind == CATALYST_KIND_NEGATIVE or lb.dilution for _, lb in seen)}
    if not seen:
        out["verdict"] = CATALYST_VERDICT_NONE if answered else CATALYST_VERDICT_NOT_CHECKED
        return out
    item, label = min(seen, key=lambda pair: _rank(*pair))
    out["verdict"] = {CATALYST_KIND_CATALYST: CATALYST_VERDICT_CATALYST, CATALYST_KIND_NEGATIVE: CATALYST_VERDICT_NEGATIVE,
                      CATALYST_KIND_ROUTINE: CATALYST_VERDICT_ROUTINE, CATALYST_KIND_NOISE: CATALYST_VERDICT_NOISE}[label.kind]
    out.update({"category": label.category, "strength": label.strength, "title": item.get("title"),
                "source": item.get("source"), "published_ts": item.get("published_ts"), "url": item.get("url")})
    return out

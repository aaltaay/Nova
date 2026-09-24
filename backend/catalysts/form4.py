"""What a Form 4 says: open-market purchases by the company's officers and directors (#517, ADR 024).

An insider reports a trade on Form 4 within two business days. One kind reads as a catalyst: an
**open-market purchase** -- transaction code ``P`` in the non-derivative table -- by a reporting owner
flagged officer or director: their own money, at the market's price. Grants (``A``), option
exercises (``M``), sales (``S``), gifts (``G``), tax withholding (``F``) and every other code are
compensation or selling; a 10% holder that is neither officer nor director is an investor, not the
company's management. A joint filing reports one set of trades for all its owners, so it counts when
any one of them is an officer or a director.

The live feed's Form 4 source (``catalysts/feed_form4.py``) records a purchase as an item whose
``sec_items`` carries its dollar total (``stamp``: ``P:412350``); the classifier reads it back
(``stamped_usd``) so a token buy stays routine. Pure: no I/O, no clock.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree

PURCHASE_CODE = "P"           # open market or private purchase (SEC Form 4, General Instruction 8)
ACQUIRED_CODE = "A"
_DOCUMENT_RE = re.compile(r"<ownershipDocument\b.*?</ownershipDocument>", re.S)
_STAMP_RE = re.compile(rf"^{PURCHASE_CODE}:(\d+)$")
_TRUE = frozenset({"1", "true"})
_ROLE_MAX_CHARS = 40
_OWNERS_NAMED = 2
_SUMMARY_MAX_CHARS = 2000
# Officer titles as a desk says them ("Chief Executive Officer" -> CEO); anything else is kept as filed.
_SHORT_TITLES = (("chief executive officer", "CEO"), ("chief financial officer", "CFO"),
                 ("chief operating officer", "COO"), ("chief technology officer", "CTO"))


@dataclass(frozen=True)
class Owner:
    name: str
    cik: str
    director: bool
    officer: bool
    ten_percent: bool
    officer_title: str

    @property
    def insider(self) -> bool:
        """An officer or a director -- the company's management, whose purchase is a signal."""
        return self.officer or self.director

    @property
    def role(self) -> str:
        title = self.officer_title
        for long, short in _SHORT_TITLES:
            title = re.sub(long, short, title, flags=re.I)
        parts = [title.strip() or "Officer"] if self.officer else []
        if self.director and "director" not in " ".join(parts).lower():
            parts.append("Director")
        return ", ".join(parts)[:_ROLE_MAX_CHARS] or ("10% owner" if self.ten_percent else "Other")


@dataclass(frozen=True)
class Trade:
    code: str
    shares: float | None
    price: float | None
    acquired: bool | None     # A (acquired) / D (disposed); None when the filing leaves it out
    date: str

    @property
    def value(self) -> float | None:
        if self.shares is None or self.price is None or self.shares <= 0 or self.price <= 0:
            return None
        return self.shares * self.price


@dataclass(frozen=True)
class Filing:
    document_type: str
    issuer_cik: str
    issuer_symbol: str
    owners: tuple[Owner, ...]
    trades: tuple[Trade, ...]   # the non-derivative table only


@dataclass(frozen=True)
class InsiderPurchase:
    owners: tuple[Owner, ...]   # the officers / directors reporting it
    trades: tuple[Trade, ...]   # the P rows
    shares: float
    total_usd: float            # shares x price over the rows that state a price
    unpriced: int               # P rows without a price: counted in shares, not in the total


def parse(raw: str | bytes) -> Filing | None:
    """The ownership document inside a full submission (``<acc>.txt``) or the XML itself; None when unreadable."""
    text = bytes(raw).decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
    m = _DOCUMENT_RE.search(text or "")
    if not m:
        return None
    try:
        root = ElementTree.fromstring(m.group(0))
    except ElementTree.ParseError:
        return None
    for el in root.iter():
        if isinstance(el.tag, str):
            el.tag = el.tag.rsplit("}", 1)[-1]
    return Filing(
        document_type=_text(root, "documentType"),
        issuer_cik=_cik(_text(root, "issuer/issuerCik")),
        issuer_symbol=_text(root, "issuer/issuerTradingSymbol").upper(),
        owners=tuple(_owner(el) for el in root.findall("reportingOwner")),
        trades=tuple(_trade(el) for el in root.findall("nonDerivativeTable/nonDerivativeTransaction")),
    )


def insider_purchase(filing: Filing) -> InsiderPurchase | None:
    """The filing's open-market purchases when an officer or a director reports them; None otherwise."""
    owners = tuple(o for o in filing.owners if o.insider)
    buys = tuple(t for t in filing.trades
                 if t.code == PURCHASE_CODE and t.acquired is not False and (t.shares or 0.0) > 0)
    if not owners or not buys:
        return None
    return InsiderPurchase(owners=owners, trades=buys, shares=sum(t.shares or 0.0 for t in buys),
                           total_usd=round(sum(t.value or 0.0 for t in buys), 2),
                           unpriced=sum(1 for t in buys if t.value is None))


def stamp(total_usd: float) -> str:
    """The purchase as the item's ``sec_items``: ``P:<whole dollars>``."""
    return f"{PURCHASE_CODE}:{max(0, int(round(total_usd)))}"


def stamped_usd(sec_items: str | None) -> float | None:
    """The dollar total a Form 4 item was stamped with; None when it carries no purchase stamp."""
    m = _STAMP_RE.match((sec_items or "").strip())
    return float(m.group(1)) if m else None


def money(usd: float) -> str:
    """$950, $412k, $1.2M."""
    if usd >= 1e6:
        return f"${usd / 1e6:.1f}M"
    if usd >= 1e3:
        return f"${usd / 1e3:.0f}k"
    return f"${usd:.0f}"


def title(buy: InsiderPurchase) -> str:
    """``Form 4: open-market purchase by Doe Jane (CEO), 50,000 shares ($412k)`` -- the item's headline."""
    named = [f"{o.name} ({o.role})" for o in buy.owners[:_OWNERS_NAMED]]
    more = len(buy.owners) - _OWNERS_NAMED
    who = "; ".join(named) + (f" and {more} more" if more > 0 else "")
    worth = money(buy.total_usd) if buy.total_usd > 0 else "price not stated"
    return f"Form 4: open-market purchase by {who}, {buy.shares:,.0f} shares ({worth})"


def summary(buy: InsiderPurchase) -> str:
    """Each purchase row: shares, price, date and value, as filed."""
    rows = []
    for t in buy.trades:
        price = f" at ${_price(t.price)}" if t.price else " (no price stated)"
        worth = f" = ${t.value:,.0f}" if t.value is not None else ""
        rows.append(f"{PURCHASE_CODE} {t.shares or 0:,.0f} sh{price}{' on ' + t.date if t.date else ''}{worth}")
    owners = ", ".join(f"{o.name} ({o.role})" for o in buy.owners)
    return f"Open-market purchase reported by {owners}: {'; '.join(rows)}."[:_SUMMARY_MAX_CHARS]


def _price(price: float) -> str:
    """1.655 -> 1.655, 6.0 -> 6.00: cents always, sub-cent digits as filed (weighted averages)."""
    text = f"{price:,.4f}".rstrip("0")
    return text if len(text.rsplit(".", 1)[-1]) >= 2 else f"{price:,.2f}"


def _node_text(node: ElementTree.Element | None) -> str:
    if node is None:
        return ""
    inner = node.find("value")   # most amounts sit in a <value> child; flags and codes are direct text
    return ((inner.text if inner is not None else node.text) or "").strip()


def _text(el: ElementTree.Element, path: str) -> str:
    return _node_text(el.find(path))


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", "")) if text else None
    except ValueError:
        return None


def _cik(text: str) -> str:
    return str(int(text)) if text.isdigit() else text


def _owner(el: ElementTree.Element) -> Owner:
    rel = el.find("reportingOwnerRelationship")

    def flag(name: str) -> bool:
        return rel is not None and _text(rel, name).lower() in _TRUE

    return Owner(name=_text(el, "reportingOwnerId/rptOwnerName"), cik=_cik(_text(el, "reportingOwnerId/rptOwnerCik")),
                 director=flag("isDirector"), officer=flag("isOfficer"), ten_percent=flag("isTenPercentOwner"),
                 officer_title=_text(rel, "officerTitle") if rel is not None else "")


def _trade(el: ElementTree.Element) -> Trade:
    ad = _text(el, "transactionAmounts/transactionAcquiredDisposedCode").upper()
    return Trade(code=_text(el, "transactionCoding/transactionCode").upper(),
                 shares=_number(_text(el, "transactionAmounts/transactionShares")),
                 price=_number(_text(el, "transactionAmounts/transactionPricePerShare")),
                 acquired=(ad == ACQUIRED_CODE) if ad else None,
                 date=_text(el, "transactionDate")[:10])

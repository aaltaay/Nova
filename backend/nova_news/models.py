"""Dataclasses for the Nova News desk."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    """One source fetch. ``articles`` are raw dicts; empty when ``ok`` is False."""

    id: str
    label: str
    ok: bool
    count: int
    error: str | None = None
    articles: list[dict] = field(default_factory=list)

    def to_public(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "ok": self.ok,
            "count": self.count,
            "error": self.error,
        }


@dataclass
class Story:
    id: str
    headline: str
    summary: str
    url: str
    source: str
    publisher: str
    outlet_kind: str
    criticality: str
    criticality_score: int
    reasons: list[str]
    symbols: list[str]
    published_at: str | None
    age_hours: float | None
    provider: str
    tags: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "headline": self.headline,
            "summary": self.summary,
            "url": self.url,
            "source": self.source,
            "publisher": self.publisher,
            "outlet_kind": self.outlet_kind,
            "criticality": self.criticality,
            "criticality_score": self.criticality_score,
            "reasons": list(self.reasons),
            "symbols": list(self.symbols),
            "published_at": self.published_at,
            "age_hours": self.age_hours,
            "provider": self.provider,
            "tags": list(self.tags),
        }

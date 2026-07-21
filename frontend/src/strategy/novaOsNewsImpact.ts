/** Pull catalyst gate news_impact evidence from a Nova OS decision. */
import type { NovaOsDecision, NovaOsGateResult } from './types';

export const NOVA_OS_GATE_CATALYST = 'catalyst';

/** Subset of backend NewsImpactVerdict.to_dict() used in Trader / Decision UX. */
export type NovaOsNewsImpactEvidence = {
  impact_class: string;
  confidence: number;
  age_bucket?: string;
  age_hours?: number | null;
  price_reaction?: string;
  attention?: string;
  source_tier?: string;
  source_name?: string | null;
  headline?: string | null;
  headline_url?: string | null;
  summary?: string;
  reasons?: string[];
  ai_reasoning?: string | null;
  sentiment?: string;
  lexicon_sentiment?: string;
};

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v != null && typeof v === 'object' && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  return null;
}

function asString(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined;
}

function asNumber(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

export function catalystGate(gates: NovaOsGateResult[]): NovaOsGateResult | null {
  return gates.find((g) => g.name === NOVA_OS_GATE_CATALYST) ?? null;
}

export function newsImpactFromEvidence(
  evidence: Record<string, unknown> | undefined | null,
): NovaOsNewsImpactEvidence | null {
  const raw = asRecord(evidence?.news_impact);
  if (!raw) return null;
  const impact_class = asString(raw.impact_class);
  const confidence = asNumber(raw.confidence);
  if (!impact_class || confidence == null) return null;

  const reasonsRaw = raw.reasons;
  const reasons = Array.isArray(reasonsRaw)
    ? reasonsRaw.filter((r): r is string => typeof r === 'string')
    : undefined;

  return {
    impact_class,
    confidence,
    age_bucket: asString(raw.age_bucket),
    age_hours: asNumber(raw.age_hours) ?? (raw.age_hours === null ? null : undefined),
    price_reaction: asString(raw.price_reaction),
    attention: asString(raw.attention),
    source_tier: asString(raw.source_tier),
    source_name: asString(raw.source_name) ?? (raw.source_name === null ? null : undefined),
    headline: asString(raw.headline) ?? (raw.headline === null ? null : undefined),
    headline_url: asString(raw.headline_url) ?? (raw.headline_url === null ? null : undefined),
    summary: asString(raw.summary),
    reasons,
    ai_reasoning:
      asString(raw.ai_reasoning) ?? (raw.ai_reasoning === null ? null : undefined),
    sentiment: asString(raw.sentiment),
    lexicon_sentiment: asString(raw.lexicon_sentiment),
  };
}

export function newsImpactFromDecision(
  decision: NovaOsDecision,
): NovaOsNewsImpactEvidence | null {
  const gate = catalystGate(decision.gates);
  return newsImpactFromEvidence(gate?.evidence ?? null);
}

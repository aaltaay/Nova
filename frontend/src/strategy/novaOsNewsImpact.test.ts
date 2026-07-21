import { describe, expect, it } from 'vitest';
import {
  catalystGate,
  newsImpactFromDecision,
  newsImpactFromEvidence,
} from './novaOsNewsImpact';
import type { NovaOsDecision } from './types';

function makeDecision(overrides: Partial<NovaOsDecision> = {}): NovaOsDecision {
  return {
    symbol: 'ABCD',
    decision: 'WAIT',
    reason_codes: ['CATALYST_WEAK'],
    mode: 'signal',
    requested_mode: 'signal',
    setup: 'gap_and_go',
    ticket: null,
    confidence: 0.55,
    gates: [
      {
        name: 'catalyst',
        passed: false,
        hard: false,
        reason_codes: ['CATALYST_WEAK'],
        evidence: {
          news_impact: {
            impact_class: 'attention_only',
            confidence: 0.42,
            age_bucket: 'fresh',
            price_reaction: 'flat',
            attention: 'elevated',
            source_tier: 'tier2',
            headline: 'Company announces update',
            reasons: ['headline_attention', 'no_price_move'],
            ai_reasoning: null,
          },
        },
      },
    ],
    citations: ['c1'],
    would_execute: false,
    executed: false,
    policy_version: 'v1',
    receipt: {
      id: 1,
      policy_version: 'v1',
      kind: 'decision',
      symbol: 'ABCD',
      decision: 'WAIT',
      action: null,
      mode: 'signal',
      reason_codes: ['CATALYST_WEAK'],
      would_execute: false,
      executed: false,
      payload: {},
    },
    ...overrides,
  };
}

describe('novaOsNewsImpact', () => {
  it('reads news_impact from catalyst gate evidence', () => {
    const d = makeDecision();
    expect(catalystGate(d.gates)?.name).toBe('catalyst');
    const news = newsImpactFromDecision(d);
    expect(news?.impact_class).toBe('attention_only');
    expect(news?.confidence).toBe(0.42);
    expect(news?.reasons).toEqual(['headline_attention', 'no_price_move']);
  });

  it('returns null when news_impact missing or incomplete', () => {
    expect(newsImpactFromEvidence({})).toBeNull();
    expect(newsImpactFromEvidence({ news_impact: { impact_class: 'x' } })).toBeNull();
  });
});

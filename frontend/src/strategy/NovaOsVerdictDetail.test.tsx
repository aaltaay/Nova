/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { NovaOsVerdictDetail } from './NovaOsVerdictDetail';
import type { NovaOsDecision } from './types';

function makeDecision(): NovaOsDecision {
  return {
    symbol: 'ABCD',
    decision: 'WAIT',
    reason_codes: ['CATALYST_WEAK'],
    mode: 'signal',
    requested_mode: 'signal',
    setup: 'gap_and_go',
    ticket: {
      entry: 10,
      stop: 9.5,
      target: 11,
      shares: 100,
      r_multiple: 2,
    },
    confidence: 0.55,
    gates: [
      {
        name: 'universe',
        passed: true,
        hard: true,
        reason_codes: ['UNIVERSE_OK'],
        evidence: {},
      },
      {
        name: 'catalyst',
        passed: false,
        hard: false,
        reason_codes: ['CATALYST_WEAK'],
        evidence: {
          news_impact: {
            impact_class: 'moved_price',
            confidence: 0.81,
            age_bucket: 'fresh',
            price_reaction: 'up',
            attention: 'high',
            source_tier: 'tier1',
            headline: 'FDA approval',
            reasons: ['price_reacted_up', 'high_confidence'],
            ai_reasoning: 'Narrative only',
          },
        },
      },
    ],
    citations: ['news.impact'],
    would_execute: false,
    executed: false,
    policy_version: 'v1',
    receipt: {
      id: 9,
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
  };
}

describe('NovaOsVerdictDetail news evidence', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders impact_class, confidence, and reason lines from news_impact', () => {
    act(() => {
      root.render(<NovaOsVerdictDetail decision={makeDecision()} compact />);
    });
    expect(container.querySelector('[data-testid="nova-os-news-impact"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="nova-os-news-impact-class"]')?.textContent).toBe(
      'moved_price',
    );
    expect(container.querySelector('[data-testid="nova-os-news-confidence"]')?.textContent).toMatch(
      /conf 81%/,
    );
    const reasons = container.querySelector('[data-testid="nova-os-news-reasons"]');
    expect(reasons?.textContent).toMatch(/price_reacted_up/);
    expect(reasons?.textContent).toMatch(/high_confidence/);
    expect(container.querySelector('[data-testid="nova-os-news-ai"]')?.textContent).toMatch(
      /Narrative only/,
    );
    expect(container.textContent).toMatch(/Entry \$10\.00/);
  });
});

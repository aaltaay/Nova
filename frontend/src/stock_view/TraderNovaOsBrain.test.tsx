/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_OS_TRADER_BRAIN_DISCLOSURE } from '../constants';
import type { NovaOsDecision } from '../strategy/types';
import { TraderNovaOsBrain } from './TraderNovaOsBrain';

function makeDecision(): NovaOsDecision {
  return {
    symbol: 'ABCD',
    decision: 'WAIT',
    reason_codes: ['CATALYST_WEAK'],
    mode: 'signal',
    requested_mode: 'signal',
    setup: 'gap_and_go',
    ticket: { entry: 2.5, stop: 2.3, target: 3, shares: 200, r_multiple: 2.5 },
    confidence: 0.6,
    gates: [
      {
        name: 'catalyst',
        passed: false,
        hard: false,
        reason_codes: ['CATALYST_WEAK'],
        evidence: {
          news_impact: {
            impact_class: 'attention_only',
            confidence: 0.33,
            reasons: ['weak_catalyst_score'],
            headline: 'Soft catalyst',
          },
        },
      },
    ],
    citations: [],
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
      reason_codes: [],
      would_execute: false,
      executed: false,
      payload: {},
    },
  };
}

describe('TraderNovaOsBrain', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => makeDecision(),
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('shows education copy, news impact, and exit note when holding', async () => {
    await act(async () => {
      root.render(
        <div className="stock-view-page">
          <TraderNovaOsBrain
            symbol="ABCD"
            position={{
              symbol: 'ABCD',
              qty: 50,
              market_price: 2.5,
              market_value: 125,
              avg_cost: 2.4,
              unrealized_pnl: 5,
              realized_pnl: 0,
            }}
          />
        </div>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector('[data-testid="trader-nova-os-brain"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="trader-nova-os-edu"]')?.textContent).toBe(
      NOVA_OS_TRADER_BRAIN_DISCLOSURE,
    );
    expect(container.querySelector('[data-testid="trader-nova-os-verdict"]')?.textContent).toMatch(
      /WAIT/,
    );
    expect(container.querySelector('[data-testid="nova-os-news-impact-class"]')?.textContent).toBe(
      'attention_only',
    );
    expect(container.querySelector('[data-testid="nova-os-news-reasons"]')?.textContent).toMatch(
      /weak_catalyst_score/,
    );
    expect(container.querySelector('[data-testid="trader-nova-os-exit-note"]')?.textContent).toMatch(
      /Holding 50/,
    );
  });

  it('surfaces loud 404 when symbol is not in scanner cache', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'ZZZZ not in scanner cache' }),
      })),
    );
    await act(async () => {
      root.render(
        <div className="stock-view-page">
          <TraderNovaOsBrain symbol="ZZZZ" />
        </div>,
      );
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="trader-nova-os-error"]')?.textContent).toMatch(
      /not in scanner cache/,
    );
  });
});

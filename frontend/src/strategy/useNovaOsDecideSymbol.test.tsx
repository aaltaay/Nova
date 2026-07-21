/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useNovaOsDecideSymbol } from './useNovaOsDecideSymbol';
import type { NovaOsDecision } from './types';

function Probe({
  symbol,
  onSnap,
}: {
  symbol: string;
  onSnap: (s: ReturnType<typeof useNovaOsDecideSymbol>) => void;
}) {
  const snap = useNovaOsDecideSymbol(symbol, true);
  onSnap(snap);
  return (
    <div data-testid="probe">
      {snap.decision?.symbol ?? 'none'}:{snap.error ?? 'ok'}
    </div>
  );
}

function decision(symbol: string): NovaOsDecision {
  return {
    symbol,
    decision: 'BUY',
    reason_codes: [],
    mode: 'signal',
    requested_mode: 'signal',
    setup: null,
    ticket: null,
    confidence: 0.9,
    gates: [],
    citations: [],
    would_execute: false,
    executed: false,
    policy_version: 'v1',
    receipt: {
      id: null,
      policy_version: 'v1',
      kind: 'decision',
      symbol,
      decision: 'BUY',
      action: null,
      mode: 'signal',
      reason_codes: [],
      would_execute: false,
      executed: false,
      payload: {},
    },
  };
}

describe('useNovaOsDecideSymbol', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useNovaOsDecideSymbol> | null;
  let resolveFetch: ((value: unknown) => void) | null;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    latest = null;
    resolveFetch = null;
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const m = String(url).match(/\/decide\/([^/?]+)/);
        const sym = decodeURIComponent(m?.[1] ?? '');
        return new Promise((resolve) => {
          resolveFetch = (overrideSym?: unknown) => {
            const out = typeof overrideSym === 'string' ? overrideSym : sym;
            resolve({
              ok: true,
              status: 200,
              json: async () => decision(out),
            });
          };
        });
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('clears prior decision immediately on symbol switch', async () => {
    await act(async () => {
      root.render(
        <Probe
          symbol="AAA"
          onSnap={(s) => {
            latest = s;
          }}
        />,
      );
    });
    expect(latest?.decision).toBeNull();

    await act(async () => {
      resolveFetch?.();
      await Promise.resolve();
    });
    expect(latest?.decision?.symbol).toBe('AAA');

    await act(async () => {
      root.render(
        <Probe
          symbol="BBB"
          onSnap={(s) => {
            latest = s;
          }}
        />,
      );
    });
    // Cleared while BBB fetch is still pending — no AAA bleed.
    expect(latest?.decision).toBeNull();
    expect(container.textContent).not.toMatch(/AAA/);

    await act(async () => {
      resolveFetch?.();
      await Promise.resolve();
    });
    expect(latest?.decision?.symbol).toBe('BBB');
  });
});

/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from '@testing-library/react';
import { useSyncExternalStore } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StockViewVenueTag } from './StockViewVenueTag';

const mocks = vi.hoisted(() => ({
  mode: 'paper' as string,
  venue: undefined as string | undefined,
  clock: null as Record<string, unknown> | null,
  version: 0,
  listeners: new Set<() => void>(),
}));
/** The real hooks are subscriptions: a change re-renders the (memoized) tag without new props. */
const useMocks = () => useSyncExternalStore(
  (onChange) => { mocks.listeners.add(onChange); return () => mocks.listeners.delete(onChange); },
  () => mocks.version,
);
const changeMocks = (change: () => void) => act(() => {
  change();
  mocks.version += 1;
  for (const onChange of mocks.listeners) onChange();
});
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => { useMocks(); return { mode: mocks.mode, venue: mocks.venue }; } }));
vi.mock('../sim/useSimReplayTarget', () => ({
  useSimReplayTarget: () => { useMocks(); return { sim: mocks.mode === 'sim', clock: mocks.clock, target: { kind: 'ok' } }; },
}));

afterEach(cleanup);

describe('StockViewVenueTag', () => {
  it('Paper: PAPER · fills est, with the practice-account tooltip', () => {
    mocks.mode = 'paper';
    render(<StockViewVenueTag symbol="GRML" />);
    const tag = screen.getByTestId('stock-view-venue-tag');
    expect(tag.textContent).toBe('PAPER· fills est');
    expect(tag.title).toMatch(/fake money/);
    expect(tag.title).not.toMatch(/IBKR paper account/);
  });

  it('Sim: says live edge at the edge and replay off it', () => {
    mocks.mode = 'sim';
    mocks.clock = { sim: true, live_edge: true };
    render(<StockViewVenueTag symbol="GRML" />);
    expect(screen.getByTestId('stock-view-venue-tag').textContent).toBe('SIM· live edge· fills est');
    changeMocks(() => { mocks.clock = { sim: true, live_edge: false, replay_source: 'historical' }; });
    expect(screen.getByTestId('stock-view-venue-tag').textContent).toBe('SIM· replay· fills est');
  });

  it('Sim with nothing loaded says so, never "replay" (QA V38)', () => {
    mocks.mode = 'sim';
    mocks.clock = { sim: true, live_edge: false, replay_source: 'none' };
    render(<StockViewVenueTag symbol="GRML" />);
    expect(screen.getByTestId('stock-view-venue-tag').textContent).toBe('SIM· no replay· fills est');
  });

  it('reads the venue, not the Gateway port label (ADR 020)', () => {
    // Live on the by-hand paper Gateway: mode says "paper", the venue is live.
    mocks.mode = 'paper';
    mocks.venue = 'live';
    render(<StockViewVenueTag symbol="GRML" />);
    expect(screen.queryByTestId('stock-view-venue-tag')).toBeNull();
    mocks.venue = undefined;
  });

  it('Live and disconnected carry no est marker at all', () => {
    for (const mode of ['live', 'disconnected']) {
      mocks.mode = mode;
      render(<StockViewVenueTag symbol="GRML" />);
      expect(screen.queryByTestId('stock-view-venue-tag')).toBeNull();
      cleanup();
    }
  });
});

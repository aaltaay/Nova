/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StockViewVenueTag } from './StockViewVenueTag';

const mocks = vi.hoisted(() => ({ mode: 'paper' as string, clock: null as Record<string, unknown> | null }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: mocks.mode }) }));
vi.mock('../sim/useSimReplayTarget', () => ({
  useSimReplayTarget: () => ({ sim: mocks.mode === 'sim', clock: mocks.clock, target: { kind: 'ok' } }),
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
    const view = render(<StockViewVenueTag symbol="GRML" />);
    expect(screen.getByTestId('stock-view-venue-tag').textContent).toBe('SIM· live edge· fills est');
    mocks.clock = { sim: true, live_edge: false };
    view.rerender(<StockViewVenueTag symbol="GRML" />);
    expect(screen.getByTestId('stock-view-venue-tag').textContent).toBe('SIM· replay· fills est');
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

/**
 * @vitest-environment jsdom
 *
 * The capacity strip (desk-ops.md, "IBKR capacity on the desk"): each IBKR cap used of its cap, who uses it on
 * hover, and a stated unread -- never a guessed count.
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { CapacityStrip } from './CapacityStrip';
import { clock, parseCapacity, toneOf } from './capacityRead';

afterEach(() => cleanup());

const ANSWER = {
  schema_version: 1,
  generated_at: 1,
  l1: { used: 48, cap: 53, cap_learned: true, reserve: 5, refused: 0, by_owner: { scanner: 45, hod: 23, live_trader: 2 } },
  l2: { used: 3, cap: 3, symbols: [{ symbol: 'AAPL', held_by: 'tab' }, { symbol: 'AEHL', held_by: 'auto_record' }, { symbol: 'CHPX', held_by: 'auto_record' }] },
  history: { used: 60, cap: 60, window_sec: 600, next_free_sec: 147.4, by_kind: { charts: 5, tape: 10, daily: 40, market: 5 } },
  tape: { used: 4, cap: null, symbols: ['AAPL', 'NFLX'] },
};

// A plain answer, not a Response: CI's Node 20 jsdom breaks a Response built in the test.
const answering = (body: unknown, status = 200) =>
  (async () => ({ ok: status < 400, status, json: async () => body })) as unknown as typeof fetch;

describe('capacity strip', () => {
  it('shows each cap used of its cap, red when full, amber from 80%', async () => {
    render(<CapacityStrip fetchImpl={answering(ANSWER)} pollMs={60_000} />);
    await waitFor(() => expect(screen.getByTestId('capacity-l1').textContent).toContain('48 / 53'));
    expect(screen.getByTestId('capacity-l1').getAttribute('data-tone')).toBe('warn');
    expect(screen.getByTestId('capacity-l2').getAttribute('data-tone')).toBe('full');
    expect(screen.getByTestId('capacity-history').textContent).toContain('60 / 60');
    expect(screen.getByTestId('capacity-history').textContent).toContain('next in 2:28');
    expect(screen.getByTestId('capacity-tape').textContent).toContain('4');
    expect(screen.getByTestId('capacity-l1').getAttribute('title')).toContain('Live Trader bot: 2');
    expect(screen.getByTestId('capacity-history').getAttribute('title')).toContain('Daily bars: SSR, Market ETFs, Cryptos: 40');
  });

  it('says it could not read, never a guessed count', async () => {
    render(<CapacityStrip fetchImpl={answering({ detail: { why: 'IBKR is not connected' } }, 503)} pollMs={60_000} />);
    await waitFor(() => expect(screen.getByTestId('capacity-strip').textContent).toContain('Capacity: not read -- IBKR is not connected'));
  });

  it('reads only a schema it knows', () => {
    expect(parseCapacity({ ...ANSWER, schema_version: 2 })).toBeNull();
    expect(parseCapacity({ ...ANSWER, l1: { used: 'x' } })).toBeNull();
    const m = parseCapacity(ANSWER)!;
    expect(toneOf(m.tape)).toBe('ok');
    expect(toneOf({ used: 10, cap: 53, users: [], note: null })).toBe('ok');
    expect(clock(147.4)).toBe('2:28');
  });
});

/**
 * @vitest-environment jsdom
 *
 * The futures and macro tiles (ADR 053 amendment 2026-10-13 evening): at 17:38 ET the futures read "--" through
 * CME's daily pause and every line after 16:00 piled up at the right edge. A tile now shows its last bar's close,
 * dimmed with its time, and its line runs on past the close when it trades there.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { lineSpan, QuoteTiles } from './Tiles';
import type { QuoteTile, Session } from './types';

vi.mock('../workspace', () => ({ setNavPage: vi.fn() }));

const OPEN = Date.UTC(2026, 9, 13, 13, 30) / 1000;    // 09:30 ET
const CLOSE = Date.UTC(2026, 9, 13, 20, 0) / 1000;    // 16:00 ET
const SESSION: Session = { date: '2026-10-13', phase: 'after_hours', open_at: OPEN, close_at: CLOSE, next: null, holiday: null };
const AT_1655 = CLOSE + 55 * 60;
const NOW_1738 = CLOSE + 98 * 60;

function tile(over: Partial<QuoteTile> = {}): QuoteTile {
  return {
    id: 'es', label: 'S&P 500 futures', symbol: 'ES', kind: 'future', exchange: 'CME', contract: 'ESZ6', last: 7855.5,
    prev_close: 7858, change: -2.5, change_pct: -0.03, price_basis: 'bars', data_type: 'bars', at: AT_1655,
    stale: true, line: [[OPEN - 5.5 * 3600, 7850], [AT_1655, 7855.5]], error: null, ...over,
  };
}

afterEach(cleanup);

describe('a tile’s line axis', () => {
  it('runs 04:00 to the close while the line ends before it', () => {
    expect(lineSpan(tile({ line: [[OPEN, 1], [OPEN + 600, 2]] }), SESSION)).toEqual({ from: OPEN - 5.5 * 3600, to: CLOSE });
  });

  it('runs on to the last point after the close (futures and Bitcoin trade there)', () => {
    expect(lineSpan(tile(), SESSION).to).toBe(AT_1655);
  });

  it('keeps the close with no line at all', () => {
    expect(lineSpan(tile({ line: [] }), SESSION).to).toBe(CLOSE);
  });
});

describe('a tile priced from a bar the market has not traded past', () => {
  it('shows the price, dimmed, with when it traded', () => {
    render(<QuoteTiles quotes={[tile()]} session={SESSION} now={NOW_1738} />);
    const t = screen.getByTestId('market-tile-es');
    expect(t.className).toContain('is-stale');
    expect(t.textContent).toContain('7,855.50');
    expect(t.textContent).toContain('as of 16:55');
    expect(t.textContent).not.toContain('--');
    expect(t.getAttribute('title')).toContain('Not trading now');
  });

  it('names the day when the bar is from an earlier one (a weekend)', () => {
    const saturday = NOW_1738 + 4 * 86400;
    render(<QuoteTiles quotes={[tile()]} session={SESSION} now={saturday} />);
    expect(screen.getByTestId('market-tile-es').textContent).toMatch(/as of Tue 16:55/);
  });

  it('labels a fresh bar price as bars, not stale', () => {
    render(<QuoteTiles quotes={[tile({ stale: false, at: CLOSE - 300 })]} session={SESSION} now={CLOSE} />);
    const t = screen.getByTestId('market-tile-es');
    expect(t.className).not.toContain('is-stale');
    expect(t.textContent).toContain('bars 15:55');
  });

  it('reads a backend without the stale field as before', () => {
    const { stale: _drop, ...old } = tile({ data_type: 'live', price_basis: 'last' });
    render(<QuoteTiles quotes={[old as QuoteTile]} session={SESSION} now={NOW_1738} />);
    const t = screen.getByTestId('market-tile-es');
    expect(t.className).not.toContain('is-stale');
    expect(t.textContent).not.toContain('as of');
  });

  it('dims the small-caps spread when a leg is stale, without an as-of time of its own', () => {
    const spread = tile({ id: 'small_caps', label: 'Small caps vs S&P', symbol: 'RTY - ES', kind: 'spread', contract: null,
      last: null, prev_close: null, change: null, change_pct: 0.42, line: [] });
    render(<QuoteTiles quotes={[spread]} session={SESSION} now={NOW_1738} />);
    const t = screen.getByTestId('market-tile-small_caps');
    expect(t.textContent).toContain('+0.42 pt');
    expect(t.textContent).toContain('small caps leading');
    expect(t.textContent).not.toContain('as of');
  });

  it('still says a refusal on a tile with no price', () => {
    render(<QuoteTiles quotes={[tile({ last: null, change: null, change_pct: null, stale: false, error: '10089: requires an additional subscription', line: [] })]}
      session={SESSION} now={NOW_1738} />);
    const t = screen.getByTestId('market-tile-es');
    expect(t.className).toContain('is-error');
    expect(t.textContent).toContain('10089');
  });
});

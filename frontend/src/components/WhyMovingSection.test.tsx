/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { normalizeWhyMoving } from '../hooks/useWhyMoving';
import type { WhyMovingRead } from '../types/whyMoving';
import { WhyMovingSection } from './WhyMovingSection';

const now = Date.now() / 1000;
// MSS 2026-09-23, as the backend read it.
const mss: WhyMovingRead = {
  schema_version: 1, symbol: 'MSS', generated_at: now, rules_version: 'move-rules-v1',
  likely: {
    kind: 'short_squeeze', label: 'Likely short squeeze -- no company news', confidence: 'likely',
    detail: 'Volume vs float: Float traded 312x; Short interest: 29% of float · 0.0 days to cover; Borrow (IBKR): Fee 104.9%/yr · 5K shares to lend',
  },
  checks: [
    { id: 'news', label: 'Company news', state: 'no', value: 'None since the prior close', detail: null,
      source: 'News verdict: Alpaca, Finnhub', as_of: now - 60 },
    { id: 'short_interest', label: 'Short interest', state: 'yes', value: '29% of float · 0.0 days to cover',
      detail: '88K shares short', source: 'FINRA short interest via Yahoo', as_of: null },
    { id: 'borrow', label: 'Borrow (IBKR)', state: 'yes', value: 'Fee 104.9%/yr · 5K shares to lend',
      detail: 'fee 20% -> 105% since the open', source: 'IBKR short-stock availability', as_of: now - 600 },
    { id: 'reverse_split', label: 'Reverse split', state: 'unknown', value: 'Unknown', detail: null,
      source: "Yahoo's last split", as_of: null },
  ],
};

afterEach(cleanup);
// The header shows "--" as two non-breaking hyphens so a wrap never splits it.
const HEADER = 'Likely short squeeze ‑‑ no company news';

describe('WhyMovingSection', () => {
  it('names the likely cause in the header while folded', () => {
    render(<WhyMovingSection read={mss} />);
    expect(screen.getByText(HEADER)).toBeTruthy();
    expect(document.querySelector('[data-why-kind="short_squeeze"]')?.className).toContain('wm-tone--squeeze');
    expect(document.querySelector('.wm-checks')).toBeNull();
  });

  it('opens to every check with its state, value and where it came from', () => {
    render(<WhyMovingSection read={mss} />);
    fireEvent.click(screen.getByRole('button', { name: /Why it's moving/ }));
    const rows = Array.from(document.querySelectorAll('.wm-check'));
    expect(rows.map((r) => r.getAttribute('data-state'))).toEqual(['no', 'yes', 'yes', 'unknown']);
    const borrow = document.querySelector('[data-check="borrow"]') as HTMLElement;
    expect(borrow.textContent).toContain('Fee 104.9%/yr · 5K shares to lend');
    expect(borrow.textContent).toContain('fee 20% -> 105% since the open');
    expect(borrow.title).toMatch(/^Yes · IBKR short-stock availability · as of 10m ago$/);
    expect((document.querySelector('[data-check="reverse_split"]') as HTMLElement).title).toMatch(/^Unknown/);
    expect(screen.getByText(/rules read of the facts below/)).toBeTruthy();
  });

  it('says possible when a deciding fact is unknown, and waits without inventing', () => {
    const possible = { ...mss, likely: { ...mss.likely, kind: 'unexplained', label: 'No cause found in the data', confidence: 'possible' as const } };
    render(<WhyMovingSection read={possible} />);
    expect(screen.getByText('possible')).toBeTruthy();
    cleanup();
    render(<WhyMovingSection read={null} loading />);
    expect(screen.getByText("Reading the move ...")).toBeTruthy();
  });

  it('keeps the last read on screen when a poll fails', () => {
    render(<WhyMovingSection read={mss} error="Move read failed: HTTP 500" />);
    fireEvent.click(screen.getByRole('button', { name: /Why it's moving/ }));
    expect(screen.getByRole('status').textContent).toContain('HTTP 500');
    expect(screen.getByText(HEADER)).toBeTruthy();
  });
});

describe('normalizeWhyMoving', () => {
  it('keeps a well-formed read and drops malformed checks', () => {
    const raw = { ...mss, checks: [...mss.checks, { id: 'x', label: 'Bad', state: 'maybe' }, null] };
    const out = normalizeWhyMoving(raw);
    expect(out?.checks.map((c) => c.id)).toEqual(['news', 'short_interest', 'borrow', 'reverse_split']);
  });

  it('refuses a payload without a likely cause, and reads an unknown confidence as possible', () => {
    expect(normalizeWhyMoving({ symbol: 'MSS', checks: [] })).toBeNull();
    const out = normalizeWhyMoving({ symbol: 'MSS', checks: [], likely: { kind: 'unexplained', label: 'x', confidence: 'sure' } });
    expect(out?.likely.confidence).toBe('possible');
  });
});

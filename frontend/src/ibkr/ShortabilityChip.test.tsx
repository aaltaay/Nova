/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ShortabilityChip } from './ShortabilityChip';

afterEach(() => cleanup());

describe('ShortabilityChip', () => {
  it('shows Loading when listing.ibkr is null (not Unknown)', () => {
    render(<ShortabilityChip ibkr={null} />);
    const chip = screen.getByTestId('shortability-chip');
    expect(chip.getAttribute('data-state')).toBe('loading');
    expect(chip.textContent).toMatch(/Loading/);
    expect(chip.textContent).not.toMatch(/Unknown/);
  });

  it('shows available state and shares', () => {
    render(
      <ShortabilityChip
        ibkr={{
          source: 'ibkr',
          state: 'shortable_est',
          shortable_shares: 250000,
          stale: false,
          orderable: true,
        }}
      />,
    );
    const chip = screen.getByTestId('shortability-chip');
    expect(chip.getAttribute('data-state')).toBe('shortable_est');
    expect(chip.textContent).toMatch(/Available/);
    expect(chip.textContent).toMatch(/250,000/);
  });

  it('shows stale when listing is stale', () => {
    render(
      <ShortabilityChip
        ibkr={{
          source: 'ibkr',
          state: 'shortable_est',
          shortable_shares: 1000,
          stale: true,
        }}
      />,
    );
    expect(screen.getByTestId('shortability-chip').getAttribute('data-state')).toBe(
      'stale',
    );
  });

  it('maps legacy short_type=hard_to_borrow to HTB', () => {
    render(
      <ShortabilityChip
        ibkr={{
          source: 'ibkr',
          short_type: 'hard_to_borrow',
          shortable_shares: 0,
        }}
      />,
    );
    const chip = screen.getByTestId('shortability-chip');
    expect(chip.getAttribute('data-state')).toBe('htb_likely');
    expect(chip.textContent).toMatch(/HTB/);
  });

  it("shows the trader's word and both IBKR sources on hover", () => {
    render(
      <ShortabilityChip
        ibkr={{
          source: 'ibkr', state: 'unknown', shortable_shares: null, stale: false, age_sec: 12,
          borrow: {
            schema_version: 1, term: 'NSS', chip: 'NSS', tone: 'bad', source: 'list',
            text: "NSS: IBKR's short-stock list dropped BIYA at 04:28 ET; was 10K @ 181%.",
            shares: null, level: null, fee_rate: null, list_age_sec: 300, list_note: null,
            list: { listed: false, fee_rate: null, available: null, as_of: 1791386086, changed_at: 1791398880,
              was: { listed: true, fee_rate: 181.0464, available: 10000, since: 1791397080 } },
          },
        }}
      />,
    );
    const chip = screen.getByTestId('shortability-chip');
    expect(chip.textContent).toBe('NSS');
    expect(chip.getAttribute('data-term')).toBe('NSS');
    expect(chip.className).toContain('sv-shortability-chip--nss');
    const tip = chip.getAttribute('data-tip') ?? '';
    expect(tip).toContain('Live (IBKR, 12 s ago): no share count');
    expect(tip).toMatch(/short-stock list \(as of \d\d:\d\d ET\): not listed since \d\d:\d\d ET -- was 10,000 @ 181%\/yr/);
  });
});

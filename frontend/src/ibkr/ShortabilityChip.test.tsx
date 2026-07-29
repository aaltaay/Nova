/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ShortabilityChip } from './ShortabilityChip';

afterEach(() => cleanup());

describe('ShortabilityChip', () => {
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
});

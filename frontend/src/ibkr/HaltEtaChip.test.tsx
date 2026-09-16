/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { HaltEtaChip } from './HaltEtaChip';

afterEach(() => cleanup());

const START = 1_700_000_000;

describe('HaltEtaChip', () => {
  it('renders nothing when there is no halt signal', () => {
    const { container } = render(<HaltEtaChip halt={null} nowMs={START * 1000} />);
    expect(container.querySelector('[data-testid="halt-eta-chip"]')).toBeNull();
  });

  it('renders the LULD pause label next to a stubbed fixture', () => {
    render(
      <HaltEtaChip
        halt={{
          halted: true,
          kind: 'luld',
          halt_code: 2,
          halt_start: START,
          source: 'ibkr_tick_49',
        }}
        nowMs={(START + 30) * 1000}
      />,
    );
    const chip = screen.getByTestId('halt-eta-chip');
    expect(chip.getAttribute('data-kind')).toBe('luld');
    expect(chip.textContent).toMatch(/LULD/);
    expect(chip.getAttribute('title') ?? '').toMatch(/tick 49/);
  });

  it('does not look like a Place / order control', () => {
    render(
      <HaltEtaChip
        halt={{ halted: true, kind: 'regulatory', halt_start: START }}
        nowMs={START * 1000}
      />,
    );
    const chip = screen.getByTestId('halt-eta-chip');
    expect(chip.tagName.toLowerCase()).toBe('span');
    expect(chip.closest('button')).toBeNull();
  });
});

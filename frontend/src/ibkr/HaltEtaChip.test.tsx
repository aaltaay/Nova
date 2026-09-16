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

  it('renders second-precise LULD pause next to a stubbed fixture', () => {
    render(
      <HaltEtaChip
        halt={{
          halted: true,
          kind: 'luld',
          halt_code: 2,
          halt_start: START,
          source: 'ibkr_ticker_halted',
        }}
        nowMs={(START + 102) * 1000}
      />,
    );
    const chip = screen.getByTestId('halt-eta-chip');
    expect(chip.getAttribute('data-kind')).toBe('luld');
    expect(chip.getAttribute('data-badge')).toBe('LULD');
    expect(chip.getAttribute('data-phase')).toBe('luld_pause');
    expect(chip.textContent).toBe('LULD · 1:42 · 3:18 left');
    const title = chip.getAttribute('title') ?? '';
    expect(title).toMatch(/ticker\.halted/);
    expect(title).toMatch(/not the SIP official start/);
  });

  it('auction and extended phases update the chip face', () => {
    const { rerender } = render(
      <HaltEtaChip
        halt={{ halted: true, kind: 'luld', halt_start: START }}
        nowMs={(START + 300) * 1000}
      />,
    );
    expect(screen.getByTestId('halt-eta-chip').textContent).toBe('Auction · 5:00 · 5:00 left');
    rerender(
      <HaltEtaChip
        halt={{ halted: true, kind: 'luld', halt_start: START }}
        nowMs={(START + 600) * 1000}
      />,
    );
    expect(screen.getByTestId('halt-eta-chip').textContent).toBe('Extended · no ETA');
  });

  it('late start is elapsed-only until Nasdaq official start arrives', () => {
    const { rerender } = render(
      <HaltEtaChip
        halt={{ halted: true, kind: 'luld', halt_start: START, start_late: true }}
        nowMs={(START + 102) * 1000}
      />,
    );
    const chip = screen.getByTestId('halt-eta-chip');
    expect(chip.getAttribute('data-late')).toBe('1');
    expect(chip.textContent).toBe('LULD · 1:42');
    rerender(
      <HaltEtaChip
        halt={{
          halted: true,
          kind: 'luld',
          halt_start: START,
          start_late: true,
          exchange: {
            status: 'ok',
            matched: true,
            official_halt_start: START,
            reason_code: 'LUDP',
            pause_threshold: null,
            quote_resume: null,
            trade_resume: null,
          },
        }}
        nowMs={(START + 102) * 1000}
      />,
    );
    expect(screen.getByTestId('halt-eta-chip').textContent).toBe('LULD · 1:42 · 3:18 left');
    expect(screen.getByTestId('halt-eta-chip').getAttribute('title') ?? '').toMatch(/LUDP/);
  });

  it('NEWS and UNK badges have no countdown', () => {
    const { rerender } = render(
      <HaltEtaChip
        halt={{ halted: true, kind: 'regulatory', halt_start: START }}
        nowMs={(START + 400) * 1000}
      />,
    );
    let chip = screen.getByTestId('halt-eta-chip');
    expect(chip.getAttribute('data-badge')).toBe('NEWS');
    expect(chip.textContent).toBe('NEWS · HALTED');
    rerender(
      <HaltEtaChip
        halt={{ halted: true, kind: 'unknown', halt_start: START }}
        nowMs={(START + 400) * 1000}
      />,
    );
    chip = screen.getByTestId('halt-eta-chip');
    expect(chip.getAttribute('data-badge')).toBe('UNK');
    expect(chip.textContent).toBe('UNK · HALTED');
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

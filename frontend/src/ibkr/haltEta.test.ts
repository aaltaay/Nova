import { describe, expect, it } from 'vitest';
import { HALT_LABEL_EXTENDED } from '../constantGroups/halt_eta';
import type { HaltSnapshot } from '../types/ticker';
import { formatClock, haltChipView, luldLabel } from './haltEta';

const START = 1_000_000;

function luld(haltStart = START, extra: Partial<HaltSnapshot> = {}): HaltSnapshot {
  return {
    halted: true,
    kind: 'luld',
    halt_code: 2,
    halt_start: haltStart,
    source: 'ibkr_ticker_halted',
    halt_start_source: 'observed_ticker_halted',
    ...extra,
  };
}

describe('haltChipView clock', () => {
  it('formats second-precise clocks', () => {
    expect(formatClock(0)).toBe('0:00');
    expect(formatClock(102)).toBe('1:42');
    expect(formatClock(198)).toBe('3:18');
    expect(formatClock(3661)).toBe('1:01:01');
  });

  it('LULD 0-5m shows elapsed and remaining seconds', () => {
    expect(haltChipView(luld(), START * 1000)?.label).toBe('LULD · 0:00 · 5:00 left');
    expect(haltChipView(luld(), (START + 102) * 1000)?.label).toBe('LULD · 1:42 · 3:18 left');
    expect(haltChipView(luld(), (START + 270) * 1000)?.label).toBe('LULD · 4:30 · 0:30 left');
  });

  it('LULD 5-10m is the auction window', () => {
    expect(haltChipView(luld(), (START + 300) * 1000)?.label).toBe('Auction · 5:00 · 5:00 left');
    expect(haltChipView(luld(), (START + 420) * 1000)?.label).toBe('Auction · 7:00 · 3:00 left');
    expect(haltChipView(luld(), (START + 420) * 1000)?.phase).toBe('luld_auction');
  });

  it('LULD >10m is Extended with no ETA', () => {
    const atTen = haltChipView(luld(), (START + 600) * 1000);
    expect(atTen?.label).toBe(HALT_LABEL_EXTENDED);
    expect(atTen?.phase).toBe('luld_extended');
    expect(luldLabel(1800)).toBe(HALT_LABEL_EXTENDED);
    expect(atTen?.label.includes('left')).toBe(false);
  });

  it('late start without official RSS is elapsed-only', () => {
    const view = haltChipView(luld(START, { start_late: true }), (START + 102) * 1000);
    expect(view?.label).toBe('LULD · 1:42');
    expect(view?.label.includes('left')).toBe(false);
    expect(view?.startLate).toBe(true);
    expect(view?.tooltip).toMatch(/observed late/i);
  });

  it('late start plus official RSS start uses the official clock', () => {
    const view = haltChipView(
      luld(START + 90, {
        start_late: true,
        exchange: {
          status: 'ok',
          matched: true,
          reason_code: 'LUDP',
          pause_threshold: '4.25',
          official_halt_start: START,
          quote_resume: START + 300,
          trade_resume: START + 600,
        },
      }),
      (START + 102) * 1000,
    );
    expect(view?.label).toBe('LULD · 1:42 · 3:18 left');
    expect(view?.tooltip).toMatch(/LUDP/);
    expect(view?.tooltip).toMatch(/4\.25/);
    expect(view?.tooltip).toMatch(/Nasdaq/i);
  });

  it('RSS miss marks exchange pending and invents no resume', () => {
    const view = haltChipView(
      luld(START, {
        exchange: {
          status: 'pending',
          matched: false,
          official_halt_start: null,
          quote_resume: null,
          trade_resume: null,
        },
      }),
      (START + 30) * 1000,
    );
    expect(view?.exchangeStatus).toBe('pending');
    expect(view?.tooltip).toMatch(/Exchange detail pending/);
    expect(view?.tooltip).not.toMatch(/99:99/);
  });

  it('clears when not halted', () => {
    expect(haltChipView(null, START * 1000)).toBeNull();
    expect(haltChipView({ halted: false, kind: 'luld' }, START * 1000)).toBeNull();
  });

  it('regulatory is NEWS with no timer', () => {
    const view = haltChipView(
      {
        halted: true,
        kind: 'regulatory',
        halt_code: 1,
        halt_start: START,
        reason: 'General halt -- news / regulatory (IBKR tick 49=1)',
      },
      (START + 400) * 1000,
    );
    expect(view?.label).toBe('NEWS · HALTED');
    expect(view?.badge).toBe('NEWS');
    expect(view?.tooltip).toMatch(/no timed reopen estimate/);
    expect(view?.label.includes('left')).toBe(false);
  });

  it('unknown is UNK + HALTED', () => {
    const view = haltChipView(
      { halted: true, kind: 'unknown', halt_start: START },
      (START + 120) * 1000,
    );
    expect(view?.label).toBe('UNK · HALTED');
    expect(view?.badge).toBe('UNK');
  });

  it('tooltip says halt start is observed, not SIP', () => {
    const view = haltChipView(luld(), START * 1000);
    expect(view?.tooltip).toMatch(/observed first ticker\.halted/i);
    expect(view?.tooltip).toMatch(/not the SIP official start/i);
    expect(view?.tooltip).toMatch(/incoming tick type 49/i);
  });
});

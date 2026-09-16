import { describe, expect, it } from 'vitest';
import { HALT_LABEL_STILL } from '../constantGroups/halt_eta';
import type { HaltSnapshot } from '../types/ticker';
import { haltChipView, luldLabel } from './haltEta';

const START = 1_000_000;

function luld(haltStart = START): HaltSnapshot {
  return {
    halted: true,
    kind: 'luld',
    halt_code: 2,
    halt_start: haltStart,
    source: 'ibkr_tick_49',
  };
}

describe('haltChipView clock', () => {
  it('LULD 0-5m shows remaining pause minutes', () => {
    expect(haltChipView(luld(), START * 1000)?.label).toBe('LULD · ~5m left');
    expect(haltChipView(luld(), (START + 90) * 1000)?.label).toBe('LULD · ~4m left');
    expect(haltChipView(luld(), (START + 270) * 1000)?.label).toBe('LULD · ~1m left');
  });

  it('LULD 5-10m is the extended auction window', () => {
    expect(haltChipView(luld(), (START + 300) * 1000)?.label).toBe('Extended · ~5m');
    expect(haltChipView(luld(), (START + 420) * 1000)?.label).toBe('Extended · ~3m');
  });

  it('LULD >10m drops the confident countdown', () => {
    const atTen = haltChipView(luld(), (START + 600) * 1000);
    expect(atTen?.label).toBe(HALT_LABEL_STILL);
    expect(atTen?.phase).toBe('luld_still');
    expect(luldLabel(1800)).toBe(HALT_LABEL_STILL);
  });

  it('clears when not halted', () => {
    expect(haltChipView(null, START * 1000)).toBeNull();
    expect(haltChipView({ halted: false, kind: 'luld' }, START * 1000)).toBeNull();
  });

  it('regulatory has reason and no timer', () => {
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
    expect(view?.label).toBe('HALTED · news/regulatory');
    expect(view?.tooltip).toMatch(/no timed reopen estimate/);
    expect(view?.label.includes('~')).toBe(false);
  });

  it('unknown is HALTED + ETA unknown', () => {
    const view = haltChipView(
      { halted: true, kind: 'unknown', halt_start: START },
      (START + 120) * 1000,
    );
    expect(view?.label).toBe('HALTED · ETA unknown');
  });
});

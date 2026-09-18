import { describe, expect, it } from 'vitest';
import {
  FILL_LATENCY_EM_DASH,
  fillLatencyFaceMs,
  fillLatencyTone,
  fillLatencyTooltip,
  formatFillLatencyMs,
  isInvalidFillClock,
  submitToFillMs,
} from './orderFillLatency';
import type { OrderFillAudit } from './types';

const FILLED_OK: OrderFillAudit = {
  place_to_submit_ms: 12,
  place_to_fill_ms: 180,
  place_to_terminal_ms: null,
  level: 'ok',
  reason: 'filled',
};

const FILLED_WARN: OrderFillAudit = {
  place_to_submit_ms: 100,
  place_to_fill_ms: 2100,
  level: 'warn',
  reason: 'mkt_rth_slow',
};

const FILLED_DANGER: OrderFillAudit = {
  place_to_submit_ms: 80,
  place_to_fill_ms: 11000,
  level: 'danger',
  reason: 'mkt_rth_slow',
};

const TERMINAL_ONLY: OrderFillAudit = {
  place_to_submit_ms: 15,
  place_to_fill_ms: null,
  place_to_terminal_ms: 3000,
  level: 'ok',
  reason: 'terminal',
};

const IMCC_REFUSED: OrderFillAudit = {
  place_to_submit_ms: -1,
  place_to_fill_ms: null,
  place_to_terminal_ms: null,
  level: 'warn',
  reason: 'timezone_shaped_clock',
};

describe('orderFillLatency', () => {
  it('formats every step in milliseconds, including negatives', () => {
    expect(formatFillLatencyMs(180)).toBe('180ms');
    expect(formatFillLatencyMs(999)).toBe('999ms');
    expect(formatFillLatencyMs(1000)).toBe('1000ms');
    expect(formatFillLatencyMs(1200)).toBe('1200ms');
    expect(formatFillLatencyMs(2100)).toBe('2100ms');
    expect(formatFillLatencyMs(11000)).toBe('11000ms');
    expect(formatFillLatencyMs(-1)).toBe('-1ms');
    expect(formatFillLatencyMs(14403037)).toBe('14403037ms');
  });

  it('missing audit is an em dash -- never invents ms', () => {
    expect(formatFillLatencyMs(null)).toBe(FILL_LATENCY_EM_DASH);
    expect(formatFillLatencyMs(undefined)).toBe(FILL_LATENCY_EM_DASH);
    expect(fillLatencyFaceMs(null)).toBeNull();
    expect(fillLatencyFaceMs({})).toBeNull();
    expect(fillLatencyTone(null)).toBeNull();
    expect(fillLatencyTooltip(null)).toBeUndefined();
  });

  it('face is click-to-fill when filled, else click-to-terminal', () => {
    expect(fillLatencyFaceMs(FILLED_OK)).toBe(180);
    expect(fillLatencyFaceMs(TERMINAL_ONLY)).toBe(3000);
  });

  it('tooltip lists Nova→submit, submit→fill, click→fill as ms lines', () => {
    expect(fillLatencyTooltip(FILLED_OK)).toBe(
      'Nova → submit: 12ms\nSubmit → fill: 168ms\nClick → fill: 180ms',
    );
    expect(submitToFillMs(FILLED_OK)).toBe(168);
  });

  it('tooltip uses click→terminal when there is no fill', () => {
    expect(fillLatencyTooltip(TERMINAL_ONLY)).toBe(
      'Nova → submit: 15ms\nSubmit → fill: —\nClick → terminal: 3000ms',
    );
  });

  it('hover shows negative submit as ms, not an em dash', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: -1,
      place_to_fill_ms: 3038,
      level: 'warn',
      reason: 'mkt_rth_slow',
    };
    expect(fillLatencyTooltip(audit)).toBe(
      'Nova → submit: -1ms\nSubmit → fill: 3039ms\nClick → fill: 3038ms',
    );
  });

  it('timezone-shaped clock blanks the face and warns on hover', () => {
    expect(isInvalidFillClock(IMCC_REFUSED)).toBe(true);
    expect(fillLatencyFaceMs(IMCC_REFUSED)).toBeNull();
    expect(fillLatencyTone(IMCC_REFUSED)).toBe('warn');
    expect(formatFillLatencyMs(fillLatencyFaceMs(IMCC_REFUSED))).toBe(
      FILL_LATENCY_EM_DASH,
    );
    expect(fillLatencyTooltip(IMCC_REFUSED)).toBe(
      'Nova → submit: -1ms\nSubmit → fill: —\nClick → fill: —\nClock: invalid (timezone_shaped_clock)',
    );
  });

  it('IMCC BUY 106411 clock skew blanks the face and explains hover', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: -296,
      place_to_fill_ms: -296,
      level: 'ok',
      reason: 'clock_skew',
    };
    expect(fillLatencyFaceMs(audit)).toBeNull();
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe(FILL_LATENCY_EM_DASH);
    expect(fillLatencyTone(audit)).toBe('ok');
    expect(fillLatencyTooltip(audit)).toBe(
      'Clocks disagree by 296ms -- not a real negative fill\nNova → submit (raw): -296ms',
    );
    expect(fillLatencyTooltip(audit)).not.toContain('Click → fill');
  });

  it('negative fill without reason is still blank -- never a -296ms face', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: -296,
      place_to_fill_ms: -296,
      level: 'ok',
      reason: 'filled',
    };
    expect(fillLatencyFaceMs(audit)).toBeNull();
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe(FILL_LATENCY_EM_DASH);
    expect(fillLatencyTooltip(audit)).toContain(
      'Clocks disagree by 296ms -- not a real negative fill',
    );
  });

  it('IMCC SELL 3037ms warn face is unchanged', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: -1,
      place_to_fill_ms: 3037,
      level: 'warn',
      reason: 'mkt_rth_slow',
    };
    expect(fillLatencyFaceMs(audit)).toBe(3037);
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe('3037ms');
    expect(fillLatencyTone(audit)).toBe('warn');
    expect(fillLatencyTooltip(audit)).toBe(
      'Nova → submit: -1ms\nSubmit → fill: 3038ms\nClick → fill: 3037ms',
    );
  });

  it('colors warn/danger from classify_fill_audit level only', () => {
    expect(fillLatencyTone(FILLED_OK)).toBe('ok');
    expect(fillLatencyTone(FILLED_WARN)).toBe('warn');
    expect(fillLatencyTone(FILLED_DANGER)).toBe('danger');
    expect(fillLatencyTone({ level: 'danger' })).toBeNull();
  });
});

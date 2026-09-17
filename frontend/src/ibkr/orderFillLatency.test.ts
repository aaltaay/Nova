import { describe, expect, it } from 'vitest';
import {
  FILL_LATENCY_EM_DASH,
  fillLatencyFaceMs,
  fillLatencyTone,
  fillLatencyTooltip,
  formatFillLatencyMs,
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

describe('orderFillLatency', () => {
  it('formats ms and seconds like 180ms / 1.2s', () => {
    expect(formatFillLatencyMs(180)).toBe('180ms');
    expect(formatFillLatencyMs(999)).toBe('999ms');
    expect(formatFillLatencyMs(1000)).toBe('1s');
    expect(formatFillLatencyMs(1200)).toBe('1.2s');
    expect(formatFillLatencyMs(2100)).toBe('2.1s');
    expect(formatFillLatencyMs(11000)).toBe('11s');
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

  it('tooltip lists Nova→submit, submit→fill, click→fill', () => {
    expect(fillLatencyTooltip(FILLED_OK)).toBe(
      'Nova → IBKR submit: 12ms -- IBKR submit → fill: 168ms -- Click → fill: 180ms',
    );
    expect(submitToFillMs(FILLED_OK)).toBe(168);
  });

  it('tooltip uses click→terminal when there is no fill', () => {
    expect(fillLatencyTooltip(TERMINAL_ONLY)).toBe(
      'Nova → IBKR submit: 15ms -- IBKR submit → fill: — -- Click → terminal: 3s',
    );
  });

  it('colors warn/danger from classify_fill_audit level only', () => {
    expect(fillLatencyTone(FILLED_OK)).toBe('ok');
    expect(fillLatencyTone(FILLED_WARN)).toBe('warn');
    expect(fillLatencyTone(FILLED_DANGER)).toBe('danger');
    expect(fillLatencyTone({ level: 'danger' })).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';
import {
  FILL_LATENCY_EM_DASH,
  FILL_LATENCY_UNAVAILABLE,
  fillLatencyFaceMs,
  fillLatencyTooltip,
  formatFillLatencyMs,
} from './orderFillLatency';
import type { OrderFillAudit } from './types';

/** Ahmed follow-up fixture matrix -- face + hover, no guessed segments. */
describe('orderFillLatency fixture matrix', () => {
  it('(a) honest ~3s MKT fill like IMCC SELL 3037ms warn', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: -1,
      place_to_fill_ms: 3037,
      face_ms: 3037,
      level: 'warn',
      reason: 'mkt_rth_slow',
    };
    expect(fillLatencyFaceMs(audit)).toBe(3037);
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe('3037ms');
    expect(fillLatencyTooltip(audit)).toBe(
      'Nova → submit: -1ms\nSubmit → fill: 3038ms\nClick → fill: 3037ms',
    );
  });

  it('(b) second-rounded fill with Nova slightly after -- blank + clock_skew hover', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: -296,
      place_to_fill_ms: -296,
      face_ms: null,
      level: 'ok',
      reason: 'clock_skew',
    };
    expect(fillLatencyFaceMs(audit)).toBeNull();
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe(FILL_LATENCY_EM_DASH);
    const hover = fillLatencyTooltip(audit) ?? '';
    expect(hover).toContain('Clocks disagree by 296ms -- not a real negative fill');
    expect(hover).toContain(`Submit → fill: ${FILL_LATENCY_UNAVAILABLE}`);
    expect(hover).toContain(`Click → fill: ${FILL_LATENCY_UNAVAILABLE}`);
    expect(hover).not.toContain('Submit → fill: 0');
  });

  it('(c) EDT-shaped 4h LMT is blank; MKT residual 3037 is shown', () => {
    const lmt: OrderFillAudit = {
      place_to_submit_ms: -1,
      place_to_fill_ms: null,
      face_ms: null,
      level: 'warn',
      reason: 'timezone_shaped_clock',
    };
    expect(fillLatencyFaceMs(lmt)).toBeNull();
    expect(fillLatencyTooltip(lmt)).toContain('Clock: invalid (timezone_shaped_clock)');
    expect(fillLatencyTooltip(lmt)).toContain(`Click → fill: ${FILL_LATENCY_UNAVAILABLE}`);

    const mkt: OrderFillAudit = {
      place_to_submit_ms: -1,
      place_to_fill_ms: 3037,
      face_ms: 3037,
      level: 'warn',
      reason: 'mkt_rth_slow',
    };
    expect(fillLatencyFaceMs(mkt)).toBe(3037);
  });

  it('(d) missing filled_at / face_ms is an em dash', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: 12,
      place_to_fill_ms: null,
      place_to_terminal_ms: null,
      face_ms: null,
      level: 'ok',
      reason: 'filled',
    };
    expect(fillLatencyFaceMs(audit)).toBeNull();
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe(FILL_LATENCY_EM_DASH);
    expect(fillLatencyTooltip(audit)).toBe(
      `Nova → submit: 12ms\nSubmit → fill: ${FILL_LATENCY_UNAVAILABLE}\nClick → fill: ${FILL_LATENCY_UNAVAILABLE}`,
    );
  });

  it('(f) hour-skew residual 0 is an em dash -- never a false 0ms fill', () => {
    const audit: OrderFillAudit = {
      place_to_submit_ms: 551,
      place_to_fill_ms: 0,
      face_ms: 0,
      level: 'ok',
      reason: 'filled',
    };
    expect(fillLatencyFaceMs(audit)).toBeNull();
    expect(formatFillLatencyMs(fillLatencyFaceMs(audit))).toBe(FILL_LATENCY_EM_DASH);
    expect(formatFillLatencyMs(0)).toBe(FILL_LATENCY_EM_DASH);

    const shaped: OrderFillAudit = {
      place_to_submit_ms: 551,
      place_to_fill_ms: null,
      face_ms: null,
      level: 'warn',
      reason: 'timezone_shaped_clock',
    };
    expect(fillLatencyFaceMs(shaped)).toBeNull();
    expect(formatFillLatencyMs(fillLatencyFaceMs(shaped))).toBe(FILL_LATENCY_EM_DASH);
  });

  it('(e) hover lists every step as ms or unavailable -- never a guessed 0ms fill', () => {
    const hover = fillLatencyTooltip({
      place_to_submit_ms: -296,
      place_to_fill_ms: -296,
      face_ms: null,
      reason: 'clock_skew',
    });
    expect(hover).toContain('Nova → submit:');
    expect(hover).toContain('Submit → fill:');
    expect(hover).toContain('Click → fill:');
    expect(hover).not.toMatch(/Submit → fill: -?\d+ms/);
    expect(hover).not.toMatch(/Click → fill: -?\d+ms/);
  });
});

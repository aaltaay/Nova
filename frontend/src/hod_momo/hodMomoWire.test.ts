import { describe, expect, it } from 'vitest';
import { alertIdentity, parseHodFrame, scrubNonFiniteTokens, uniqueAlerts } from './hodMomoWire';
import type { AlertObject } from './types';

function alert(id: string, created: number, ticker = 'VEEE'): AlertObject {
  return {
    id, timestamp: '2026-09-22T02:29:05.000Z', ticker, strategy_id: 12, strategy_name: 'Running Up Alert',
    price: 16.95, change_pct: null, rvol: null, float_shares: null, gap_pct: null, volume: null,
    momentum_pct: null, rvol_source: null, consolidation_count: 1, consolidated_ids: [], created_ts: created,
  };
}

describe('parseHodFrame (QA C32)', () => {
  it('reads an initial message that carries a bare NaN instead of dropping the day', () => {
    const raw = '{"type":"initial","alerts":[{"id":"a","ticker":"NAN","rvol":NaN,"gap_pct":-Infinity,"x":Infinity}],"total":1}';
    expect(() => JSON.parse(raw)).toThrow();
    const msg = parseHodFrame(raw) as { alerts: Array<Record<string, unknown>> };
    expect(msg.alerts[0]).toEqual({ id: 'a', ticker: 'NAN', rvol: null, gap_pct: null, x: null });
  });

  it('never touches text inside strings, and escaped quotes stay strings', () => {
    const raw = '{"note":"NaN \\"Infinity\\" -Infinity","v":NaN}';
    expect(scrubNonFiniteTokens(raw)).toBe('{"note":"NaN \\"Infinity\\" -Infinity","v":null}');
    expect(scrubNonFiniteTokens('{"v":-1.5}')).toBe('{"v":-1.5}');
  });

  it('returns undefined for a frame that still cannot be read', () => {
    expect(parseHodFrame('{"type":')).toBeUndefined();
    expect(parseHodFrame('{"type":"ping"}')).toEqual({ type: 'ping' });
  });
});

describe('uniqueAlerts (QA V16)', () => {
  it('drops exact repeats but keeps two alerts that share a legacy id', () => {
    const a = alert('1790044145000-VEEE-12', 1790046256.1);
    const b = alert('1790044145000-VEEE-12', 1790046029.8);
    const out = uniqueAlerts([a, b, { ...a }]);
    expect(out).toHaveLength(2);
    expect(new Set(out.map(alertIdentity)).size).toBe(2);
  });
});

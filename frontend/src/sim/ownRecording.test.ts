import { describe, expect, it } from 'vitest';
import { etDateToday, ownRecordingFor } from './ownRecording';
import { simTabOwnRecording } from './simConstants';

const sessions = {
  days: [],
  tickers_by_day: {
    '2026-09-21': [{ symbol: 'GRML', prints: 16275, l2: 3282, usable: true, empty: false, status: 'recording' }],
    '2026-09-19': [
      { symbol: 'GRML', prints: 900, l2: 10, usable: true, empty: false, status: 'stopped_partial_ok' },
      { symbol: 'SPY', prints: 0, l2: 0, usable: false, empty: true, unavailable_reason: 'No recorded prints or quotes' },
    ],
  },
};

describe('ownRecordingFor', () => {
  it('prefers today\'s recording of the symbol and says it is still recording', () => {
    expect(ownRecordingFor(sessions, 'grml', '2026-09-21')).toEqual({
      date: '2026-09-21', symbol: 'GRML', prints: 16275, recording: true,
    });
  });

  it('falls back to the newest older day when today has nothing, and never calls it still recording', () => {
    expect(ownRecordingFor(sessions, 'GRML', '2026-09-22')).toEqual({
      date: '2026-09-21', symbol: 'GRML', prints: 16275, recording: false,
    });
  });

  it('never offers an empty or unusable recording, and nothing for an unrecorded symbol', () => {
    expect(ownRecordingFor(sessions, 'SPY', '2026-09-21')).toBeNull();
    expect(ownRecordingFor(sessions, 'QNME', '2026-09-21')).toBeNull();
    expect(ownRecordingFor(null, 'GRML')).toBeNull();
  });

  it('never offers the removed synthetic SIM1 session, and an uncounted recording never reads -1 (C21 / C22)', () => {
    const synthetic = { days: [], tickers_by_day: { '2026-09-19': [
      { symbol: 'SIM1', prints: 172020, l2: 5, usable: true, source: 'sim', status: 'generated_full_day' },
    ] } };
    expect(ownRecordingFor(synthetic, 'SIM1', '2026-09-22')).toBeNull();
    const running = { days: [], tickers_by_day: { '2026-09-22': [
      { symbol: 'GDC', prints: null, l2: null, usable: true, source: 'ibkr', status: 'recording' },
    ] } };
    const own = ownRecordingFor(running, 'GDC', '2026-09-22')!;
    expect(own).toEqual({ date: '2026-09-22', symbol: 'GDC', prints: null, recording: true });
    const line = simTabOwnRecording(own.symbol, own.date, own.prints, own.recording);
    expect(line).not.toMatch(/-1/);
    expect(line).toMatch(/prints recorded, still recording/);
  });

  it('points at the control that exists: the Sim strip menu, not "Day / Ticker above" (V20)', () => {
    const line = simTabOwnRecording('GRML', '2026-09-21', 20969, false);
    expect(line).toMatch(/20,969 prints/);
    expect(line).toMatch(/open ⋯ on the Sim strip and pick it under Load recording/);
    expect(line).not.toMatch(/above/);
  });

  it('etDateToday reads the Eastern calendar day', () => {
    expect(etDateToday(new Date('2026-09-21T23:30:00-04:00'))).toBe('2026-09-21');
    expect(etDateToday(new Date('2026-09-22T03:59:00Z'))).toBe('2026-09-21');
  });
});

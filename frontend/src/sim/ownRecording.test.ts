import { describe, expect, it } from 'vitest';
import { etDateToday, ownRecordingFor } from './ownRecording';

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

  it('etDateToday reads the Eastern calendar day', () => {
    expect(etDateToday(new Date('2026-09-21T23:30:00-04:00'))).toBe('2026-09-21');
    expect(etDateToday(new Date('2026-09-22T03:59:00Z'))).toBe('2026-09-21');
  });
});

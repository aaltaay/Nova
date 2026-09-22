import { describe, expect, it } from 'vitest';
import { sessionChipKind, sessionChipTitle, sessionChipView } from './globalBarSession';

/** A 2026 September date at the given Eastern wall time (EDT, UTC-4). */
function et(day: number, hh: number, mm: number): Date {
  return new Date(Date.UTC(2026, 8, day, hh + 4, mm, 0));
}

describe('sessionChipView', () => {
  it('reads PREMARKET / OPEN / AFTER HOURS / CLOSED from the Eastern clock', () => {
    // Tue Sep 22 2026
    expect(sessionChipKind(et(22, 3, 59))).toBe('closed');
    expect(sessionChipKind(et(22, 4, 0))).toBe('premarket');
    expect(sessionChipKind(et(22, 9, 29))).toBe('premarket');
    expect(sessionChipKind(et(22, 9, 30))).toBe('open');
    expect(sessionChipKind(et(22, 15, 59))).toBe('open');
    expect(sessionChipKind(et(22, 16, 0))).toBe('afterhours');
    expect(sessionChipKind(et(22, 19, 59))).toBe('afterhours');
    expect(sessionChipKind(et(22, 20, 0))).toBe('closed');
    expect(sessionChipView(et(22, 8, 41)).label).toBe('PREMARKET');
    expect(sessionChipView(et(22, 12, 0)).label).toBe('OPEN');
    expect(sessionChipView(et(22, 18, 14)).label).toBe('AFTER HOURS');
    expect(sessionChipView(et(22, 23, 0)).label).toBe('CLOSED');
  });

  it('is CLOSED all weekend, even at 10:30 Saturday', () => {
    // Sat Sep 26 / Sun Sep 27 2026
    expect(sessionChipKind(et(26, 10, 30))).toBe('closed');
    expect(sessionChipKind(et(27, 8, 0))).toBe('closed');
  });

  it('names the session bounds in ET and says holidays are unknown', () => {
    expect(sessionChipTitle('premarket')).toBe(
      'Premarket session 04:00-09:30 ET. NYSE holidays are not known to the client.',
    );
    expect(sessionChipTitle('open')).toContain('09:30-16:00 ET');
    expect(sessionChipTitle('afterhours')).toContain('16:00-20:00 ET');
    expect(sessionChipTitle('closed')).not.toMatch(/\d{2}:\d{2}-\d{2}:\d{2}/);
    expect(sessionChipTitle('closed')).toContain('holidays');
  });
});

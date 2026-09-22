import { describe, expect, it } from 'vitest';
import { fmtCountdown, sessionCountdown } from './sessionCountdown';

/** 2026-09-22 is a Tuesday; EDT is UTC-4. */
function et(hhmmss: string, date = '2026-09-22'): Date {
  return new Date(`${date}T${hhmmss}-04:00`);
}

describe('sessionCountdown', () => {
  it('counts down to the 09:30 open before the open', () => {
    const c = sessionCountdown(et('08:41:07'));
    expect(c.dateLabel).toBe('Tue Sep 22');
    expect(c.phase).toBe('opens');
    expect(c.phaseLabel).toBe('Opens in');
    expect(c.countdown).toBe('48:53');
  });

  it('counts down to the 16:00 close during regular hours', () => {
    const c = sessionCountdown(et('09:30:00'));
    expect(c.phase).toBe('closes');
    expect(c.countdown).toBe('6:30:00');
    expect(sessionCountdown(et('15:59:59')).countdown).toBe('00:01');
  });

  it('says After hours from the close on, with no countdown', () => {
    const c = sessionCountdown(et('16:00:00'));
    expect(c.phase).toBe('afterhours');
    expect(c.phaseLabel).toBe('After hours');
    expect(c.countdown).toBeNull();
    expect(sessionCountdown(et('22:15:00')).phase).toBe('afterhours');
  });

  it('counts a weekend down to Monday 09:30', () => {
    // Saturday 2026-09-26 10:00 ET -> Monday 09:30 is 1d 23:30 away.
    const sat = sessionCountdown(et('10:00:00', '2026-09-26'));
    expect(sat.phase).toBe('opens');
    expect(sat.countdown).toBe('47:30:00');
    const sun = sessionCountdown(et('10:00:00', '2026-09-27'));
    expect(sun.countdown).toBe('23:30:00');
  });

  it('formats mm:ss under an hour and h:mm:ss above', () => {
    expect(fmtCountdown(59)).toBe('00:59');
    expect(fmtCountdown(3600)).toBe('1:00:00');
    expect(fmtCountdown(-5)).toBe('00:00');
  });
});

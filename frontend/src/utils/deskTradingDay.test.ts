import { describe, expect, it } from 'vitest';
import { todayPracticeDate } from '../account/accountFigures';
import { deskTradingDay } from './deskTradingDay';

// 2026-10-19 is a Monday; the clock is read at 00:30 ET, 10:00 ET and Saturday 10:00 ET.
describe('deskTradingDay', () => {
  it('Monday 00:30 ET still belongs to the weekend, so to Friday', () => {
    expect(deskTradingDay(Date.parse('2026-10-19T04:30:00.000Z'))).toBe('2026-10-16');
  });

  it('Monday 10:00 ET is Monday', () => {
    expect(deskTradingDay(Date.parse('2026-10-19T14:00:00.000Z'))).toBe('2026-10-19');
  });

  it('Saturday 10:00 ET and Sunday 10:00 ET are Friday', () => {
    expect(deskTradingDay(Date.parse('2026-10-17T14:00:00.000Z'))).toBe('2026-10-16');
    expect(deskTradingDay(Date.parse('2026-10-18T14:00:00.000Z'))).toBe('2026-10-16');
  });

  it('Saturday 04:00 ET is no rollover; Friday 03:59 ET still belongs to Thursday', () => {
    expect(deskTradingDay(Date.parse('2026-10-17T07:59:00.000Z'))).toBe('2026-10-16');
    expect(deskTradingDay(Date.parse('2026-10-17T08:00:00.000Z'))).toBe('2026-10-16');
    expect(deskTradingDay(Date.parse('2026-10-16T07:59:00.000Z'))).toBe('2026-10-15');
  });

  it('Friday evening stays Friday through the weekend', () => {
    expect(deskTradingDay(Date.parse('2026-10-17T00:30:00.000Z'))).toBe('2026-10-16'); // Fri 20:30 ET
  });
});

describe('todayPracticeDate', () => {
  it("is the desk's trading day, so Day P&L keys Friday's row on Saturday", () => {
    expect(todayPracticeDate(new Date('2026-10-17T14:00:00.000Z'))).toBe('2026-10-16');
    expect(todayPracticeDate(new Date('2026-10-19T14:00:00.000Z'))).toBe('2026-10-19');
    expect(todayPracticeDate(new Date('2026-10-19T04:30:00.000Z'))).toBe('2026-10-16');
  });
});

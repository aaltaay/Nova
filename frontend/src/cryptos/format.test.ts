import { describe, expect, it } from 'vitest';
import {
  ago,
  countdown,
  dateEt,
  dayTimeEt,
  funding,
  level,
  listWords,
  minutesEt,
  mult,
  pct,
  price,
  pt,
  stockPrice,
  tilePrice,
  timeEt,
  tone,
  usd,
  usdFine,
  usdSigned,
} from './format';

/** Tue 2026-09-29 23:08 ET (EDT, UTC-4). */
const TUE_2308 = Date.UTC(2026, 8, 30, 3, 8) / 1000;

describe('cryptos format', () => {
  it('writes an unknown number as a dash, never 0', () => {
    for (const f of [pct, pt, usd, usdFine, usdSigned, price, level, mult, funding, stockPrice, tilePrice, timeEt, dayTimeEt, dateEt, countdown]) {
      expect(f(null)).toBe('—');
      expect(f(undefined)).toBe('—');
      expect(f(Number.NaN)).toBe('—');
    }
    expect(tone(null)).toBe('is-flat');
    expect(ago(null, TUE_2308)).toBe('never');
  });

  it('signs percentages and points with a true minus, and no sign on zero', () => {
    expect(pct(2.14)).toBe('+2.14%');
    expect(pct(-0.2)).toBe('−0.20%');
    expect(pct(7.84, 1)).toBe('+7.8%');
    expect(pct(0)).toBe('0.00%');
    expect(pct(-0.001)).toBe('0.00%');
    expect(pt(0.4)).toBe('+0.4 pt');
    expect(pt(-1.25, 2)).toBe('−1.25 pt');
  });

  it('shortens dollars, with one more digit on a headline figure', () => {
    expect(usd(3.94e12)).toBe('$3.94T');
    expect(usd(148.2e9)).toBe('$148B');
    expect(usd(2.9e9)).toBe('$2.9B');
    expect(usd(412e6)).toBe('$412M');
    expect(usd(-88e6)).toBe('−$88M');
    expect(usdFine(148.2e9)).toBe('$148.2B');
    expect(usdFine(3.94e12)).toBe('$3.94T');
    expect(usdFine(412e6)).toBe('$412M');
    expect(usdSigned(412e6)).toBe('+$412M');
    expect(usdSigned(-88e6)).toBe('−$88M');
    expect(usdSigned(0)).toBe('$0');
  });

  it('prices a coin with the digits its size needs', () => {
    expect(price(112480)).toBe('112,480.00');
    expect(price(4212.4)).toBe('4,212.40');
    expect(price(182.5)).toBe('182.50');
    expect(price(2.4)).toBe('2.400');
    expect(price(0.1234)).toBe('0.1234');
    expect(price(0.00001234)).toBe('0.00001234');
    expect(tilePrice(112480.4)).toBe('$112,480');
    expect(tilePrice(4212.4)).toBe('$4,212.40');
    expect(tilePrice(0.5)).toBe('$0.5000');
    expect(stockPrice(63.84)).toBe('63.84');
    expect(stockPrice(1234.5)).toBe('1,234.50');
    expect(level(112480.4)).toBe('112,480');
    expect(level(182.5)).toBe('182.50');
  });

  it('writes funding to three places and multiples to one', () => {
    expect(funding(0.041)).toBe('+0.041%');
    expect(funding(-0.012)).toBe('−0.012%');
    expect(funding(0.0001)).toBe('0.000%');
    expect(mult(2.34)).toBe('2.3×');
  });

  it('reads the ET clock, midnight included', () => {
    expect(timeEt(TUE_2308)).toBe('23:08');
    expect(dayTimeEt(TUE_2308)).toBe('Tue 23:08');
    expect(dateEt(TUE_2308)).toBe('Sep 29');
    expect(timeEt(Date.UTC(2026, 8, 30, 4, 0) / 1000)).toBe('00:00');
    expect(minutesEt(240)).toBe('04:00');
    expect(minutesEt(570)).toBe('09:30');
    expect(minutesEt(1440)).toBe('00:00');
  });

  it('counts down and back in plain words', () => {
    expect(countdown(4 * 3600 + 52 * 60)).toBe('4h 52m');
    expect(countdown(720)).toBe('12m');
    expect(countdown(45)).toBe('45s');
    expect(countdown(-5)).toBe('0s');
    expect(ago(TUE_2308 - 12, TUE_2308)).toBe('12 s ago');
    expect(ago(TUE_2308 - 240, TUE_2308)).toBe('4 min ago');
    expect(ago(TUE_2308 - 7200, TUE_2308)).toBe('2 h ago');
  });

  it('lists words and colours a move', () => {
    expect(listWords([])).toBe('');
    expect(listWords(['SOL'])).toBe('SOL');
    expect(listWords(['PEPE', 'DOGE', 'SOL'])).toBe('PEPE, DOGE and SOL');
    expect(tone(1)).toBe('is-up');
    expect(tone(-1)).toBe('is-down');
    expect(tone(0)).toBe('is-flat');
  });
});

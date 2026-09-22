import { describe, expect, it } from 'vitest';
import { deskBoardEmpty } from '../constantGroups/desk';
import { focusRailEmpty } from '../constantGroups/trader_chrome';
import { depthUnavailableHint } from '../stock_view/depthUnavailableHint';
import { listAbsenceText } from './listAbsence';

describe('a mirrored list states why it is empty (QA D10)', () => {
  it('names a failing feed first', () => {
    const text = listAbsenceText('Gappers', { restError: 'Scanner feed failed: the scanner routes could not be reached', healthStatus: 'error' }, deskBoardEmpty);
    expect(text).toBe('Gappers: Scanner feed failed: the scanner routes could not be reached');
  });

  it('says a pending first load is pending', () => {
    expect(listAbsenceText('Gappers', { restError: null, healthStatus: 'loading' }, focusRailEmpty)).toBe('Gappers: waiting for the scanner feed…');
  });

  it('says "no rows right now" only for a loaded, empty list', () => {
    expect(listAbsenceText('Gappers', { restError: null, healthStatus: 'connected' }, deskBoardEmpty)).toBe('Gappers: no rows right now');
  });
});

describe('the Stock Quote card blames the Gateway only when the status says so (QA D10)', () => {
  it('asks to connect IB Gateway on a known outage', () => {
    expect(depthUnavailableHint(true, null)).toMatch(/^Connect IB Gateway/);
  });

  it('says it is checking while the status is pending, and names a failing status', () => {
    expect(depthUnavailableHint(false, null)).toMatch(/Checking IB Gateway/);
    expect(depthUnavailableHint(false, 'HTTP 500')).toMatch(/failing.*\(HTTP 500\)$/);
  });
});

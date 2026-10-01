/**
 * Not a trade (operator report, 2026-09-29: "So why does it think this is a good trade when it's
 * obviously not?"): the plan's verdict off the wire, its words, and the chart's moment -- a plan that
 * is not a trade calls no entry, and a setup that played out never reads TRIGGERED again.
 */
import { describe, expect, it } from 'vitest';
import { NOT_A_TRADE_NOVA } from './constants';
import { momentOf, type MomentInputs } from './momentModel';
import { planBadge } from './planMath';
import { gradeChip, gradeTip, normalizePlanVerdict, notATrade, resultBadge, resultBadgeShort } from './planVerdict';
import type { StockPlan } from './types';
import { inputs, pfsaAt, pfsaRead, pfsaView } from './whoTradesFixtures';
import { planActions } from './whoTradesModel';

const NOT_A_TRADE: Partial<StockPlan> = {
  grade: 'C',
  pillars: { passed: 1, known: 5, total: 5 },
  tape: { verdict: 'wait', reasons: ['no green on the tape yet'] },
  trade: { ok: false, reasons: ['grade C: 1 of 5 pillars', 'it triggered with the tape at WAIT: no green on the tape yet'] },
};
const STOPPED = {
  outcome: 'stop_first' as const, at: pfsaAt(8, 8, 47), r: -1, text: 'the stop printed first at 08:08 (-1.00R)',
};

describe('the verdict on the wire', () => {
  it('reads the count, the verdict and the result, and drops what is mistyped', () => {
    expect(normalizePlanVerdict({
      pillars: { passed: 1, known: 5, total: 5 },
      trade: { ok: false, reasons: ['grade C: 1 of 5 pillars', 7] },
      result: STOPPED,
    })).toEqual({
      pillars: { passed: 1, known: 5, total: 5 },
      trade: { ok: false, reasons: ['grade C: 1 of 5 pillars'] },
      result: STOPPED,
    });
    expect(normalizePlanVerdict({ pillars: { passed: 'x' }, trade: { ok: 'no' }, result: { outcome: 'sideways' } }))
      .toEqual({ pillars: null, trade: null, result: null });
    expect(normalizePlanVerdict({})).toEqual({ pillars: null, trade: null, result: null });
  });

  it('says it in words', () => {
    const plan = pfsaRead('triggered', NOT_A_TRADE).plan!;
    expect(gradeChip(plan)).toBe('C 1/5');
    expect(gradeTip(plan).split('\n')[0]).toBe('Grade C: 1 of 5 pillars pass.');
    expect(gradeChip({ ...plan, pillars: null })).toBe('C');
    expect(gradeChip({ ...plan, grade: null })).toBeNull();
    expect(notATrade(plan)).toBe('Not a trade: grade C: 1 of 5 pillars; it triggered with the tape at WAIT: '
      + 'no green on the tape yet.');
    expect(notATrade(pfsaRead('triggered').plan)).toBeNull();                     // a trade
    expect(notATrade(pfsaRead('triggered', { trade: null }).plan)).toBeNull();    // the operator's own plan
    expect(resultBadge(STOPPED)).toBe('STOP FIRST 08:08 · −1.00R');
    expect(resultBadge({ ...STOPPED, outcome: 'target_first', r: 1.5 })).toBe('TARGET FIRST 08:08 · +1.50R');
    expect(resultBadgeShort(STOPPED)).toBe('STOP FIRST −1.00R');
  });
});

describe('the moment on the chart', () => {
  const at = (over: Partial<MomentInputs>) => momentOf(inputs(over));

  it('a trigger that is not a trade calls no entry, whatever the tape said, and says Nova buys none of it', () => {
    const m = at({ read: pfsaRead('triggered', NOT_A_TRADE) });
    expect(m).toMatchObject({ step: 1, tone: 'wait', badge: 'FIRST PULLBACK · TRIGGERED · NOT A TRADE' });
    expect(m?.call).toMatchObject({ tone: 'wait', title: 'NOT A TRADE', ping: false });
    expect(m?.call?.detail).toBe('grade C: 1 of 5 pillars; it triggered with the tape at WAIT: no green on the tape yet. '
      + "It blocks Nova's buys too: the bot, Auto-entry and Approve do not take it.");
    const onGo = at({ read: pfsaRead('triggered', { ...NOT_A_TRADE, tape: { verdict: 'go', reasons: [] },
      trade: { ok: false, reasons: ['grade C: 3 of 5 pillars'] } }) });
    expect(onGo?.call?.title).toBe('NOT A TRADE');                                // never ENTER NOW
  });

  it('near its trigger it says not a trade instead of get ready', () => {
    const m = at({ read: pfsaRead('near', NOT_A_TRADE), now: pfsaAt(8, 7, 0) });
    expect(m).toMatchObject({ step: 0, tone: 'wait', badge: 'FIRST PULLBACK · NEAR 0.03 · NOT A TRADE' });
    expect(m?.call?.title).toBe('NOT A TRADE');
  });

  it('a setup that played out reads its result, never TRIGGERED', () => {
    const read = pfsaRead('triggered', { ...NOT_A_TRADE, result: STOPPED });
    const m = at({ read });
    expect(m).toMatchObject({ step: 1, tone: 'stop', badge: 'FIRST PULLBACK · STOP FIRST 08:08 · −1.00R', call: null });
    expect(planBadge(read.plan!, read.setups[0])).toBe('STOP FIRST 08:08 · −1.00R');
  });

  it('Approve says why instead of approving a plan that is not a trade, and that it blocks Nova too', () => {
    const i = inputs({ read: pfsaRead('armed', NOT_A_TRADE), who: pfsaView('approve') });
    const why = notATrade(i.read!.plan);
    const { actions } = planActions({ moment: momentOf(i), inputs: i, bid: 4.25, listening: true, stageLocked: why,
      notTrade: why, symbol: 'PFSA' });
    expect(actions[0]).toMatchObject({ id: 'approve', locked: `${why} ${NOT_A_TRADE_NOVA}` });
    const triggered = inputs({ read: pfsaRead('triggered', NOT_A_TRADE), who: pfsaView('approve') });
    const now = planActions({ moment: momentOf(triggered), inputs: triggered, bid: 4.25, listening: true,
      stageLocked: why, notTrade: why, symbol: 'PFSA' });
    expect(now.actions[0]).toMatchObject({ id: 'approve-now', locked: `${why} ${NOT_A_TRADE_NOVA}` });
  });
});

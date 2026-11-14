/**
 * The trade's moment on the desk (ADR 037): the moment on the chart (its track, its call and the one ping it keys),
 * the levels with what stands behind them, the Level 2 markers and the plan card's buttons -- on PFSA's first pullback
 * of 2026-09-24. Nova trades nothing by itself (ADR 072): every entry and exit is the operator's.
 */
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { inputs, PFSA_SETUP_ID, PFSA_TRIGGER, pfsaRead } from './momentFixtures';
import { momentOf, nextHeld, NO_HELD, type HeldMemory, type MomentInputs } from './momentModel';
import { planActions } from './planActions';
import { level2Markers, orderLevels } from './tradeLevels';

/** Feed the memory a sequence of looks, as the hook does. */
function remember(looks: Partial<MomentInputs>[], start: HeldMemory = NO_HELD): HeldMemory {
  return looks.reduce((held, over) => nextHeld(held, inputs(over, held)), start);
}

const HOLDING = { position: { qty: 153, avgCost: 4.27 } };

describe('the moment on the chart', () => {
  it('forming: the badge says how near, and the call says get ready', () => {
    const m = momentOf(inputs({ read: pfsaRead('near'), now: PFSA_TRIGGER - 2 }));
    expect(m).toMatchObject({ step: 0, tone: 'near', badge: 'FIRST PULLBACK · NEAR 0.03', exitLabel: 'Your exit' });
    expect(m?.call).toMatchObject({ title: 'GET READY', ping: false });
    expect(m?.call?.detail).toMatch(/Enter above 4.26/);
  });

  it('an armed or forming setup calls nothing yet', () => {
    expect(momentOf(inputs({ read: pfsaRead('armed') }))?.call ?? null).toBeNull();
    expect(momentOf(inputs({ read: pfsaRead('forming') }))?.call ?? null).toBeNull();
  });

  it('at the trigger with the tape at go: ENTER NOW, with the size and one ping', () => {
    const m = momentOf(inputs());
    expect(m).toMatchObject({ step: 1, tone: 'go', badge: 'FIRST PULLBACK · TRIGGERED' });
    expect(m?.call).toMatchObject({
      id: `enter:${PFSA_SETUP_ID}`, tone: 'go', title: 'ENTER NOW · 4.27', ping: true,
      pin: { label: 'ENTER NOW', price: 4.27, at: PFSA_TRIGGER },
    });
    expect(m?.call?.detail).toBe('4.26 printed with the tape at go. 153 shares risk $20. Your click.');
  });

  it('calls no entry when the price ran more than half a risk, the tape is not at go, or 30 s went by', () => {
    expect(momentOf(inputs({ last: 4.36 }))?.call).toMatchObject({ title: 'TRIGGERED · TOO FAR', ping: false });
    const wait = pfsaRead('triggered', { tape: { verdict: 'wait', reasons: ['sellers still hitting'] } });
    expect(momentOf(inputs({ read: wait }))?.call).toMatchObject({ title: 'TRIGGERED · TAPE WAIT', ping: false });
    expect(momentOf(inputs({ now: PFSA_TRIGGER + 31 }))?.call ?? null).toBeNull();
  });

  it('holding: in the trade with its P&L, then SELL NOW when the target prints, latched', () => {
    let held = remember([{ ...HOLDING, last: 4.40 }]);
    expect(momentOf(inputs({ ...HOLDING, last: 4.40 }, held))).toMatchObject({
      step: 2, tone: 'holding', badge: 'IN THE TRADE · +$19.89', exitLabel: 'Your exit', call: null,
    });
    held = remember([{ ...HOLDING, last: 4.52, now: PFSA_TRIGGER + 26 }], held);
    const due = momentOf(inputs({ ...HOLDING, last: 4.47, now: PFSA_TRIGGER + 27 }, held));
    expect(due).toMatchObject({ step: 3, tone: 'target', badge: 'TARGET 4.52 HIT · SELL' });
    // The id names the level, so a moved stop or target is a new call (and a new ping).
    expect(due?.call).toMatchObject({ id: `sell-target:${held.since}:4.52`, title: 'SELL NOW · TARGET 4.52', ping: true });
    expect(due?.call?.detail).toMatch(/No order is working: the exit is yours/);
  });

  it('a setup that triggers minutes into a hand trade does not lend it its stop and target', () => {
    const forming = pfsaRead('forming');
    const held = remember([
      { ...HOLDING, read: forming, last: 4.30, now: PFSA_TRIGGER - 120 },
      { ...HOLDING, last: 4.55, now: PFSA_TRIGGER + 5 },
    ]);
    expect(held.levels).toBeNull();
    expect(momentOf(inputs({ ...HOLDING, last: 4.55, now: PFSA_TRIGGER + 6 }, held))).toMatchObject({
      step: 2, badge: 'IN THE TRADE · +$42.84', call: null,
    });
  });

  it('the stop printing after the target makes the stop the call', () => {
    const held = remember([
      { ...HOLDING, last: 4.40 },
      { ...HOLDING, last: 4.52, now: PFSA_TRIGGER + 26 },
      { ...HOLDING, last: 4.13, now: PFSA_TRIGGER + 105 },
    ]);
    const m = momentOf(inputs({ ...HOLDING, last: 4.13, now: PFSA_TRIGGER + 106 }, held));
    expect(m).toMatchObject({ step: 3, tone: 'stop', badge: 'STOP 4.14 HIT · SELL' });
    expect(m?.call?.detail).toMatch(/At the stop the trade is about -\$19.89/);
  });

  it('flat after your own sale: every step done, until another setup takes the chart', () => {
    const held = remember([{ ...HOLDING, last: 4.40 }, { position: null, last: 4.50, now: PFSA_TRIGGER + 40 }]);
    expect(held.flatKey).toBe(PFSA_SETUP_ID);
    expect(momentOf(inputs({ now: PFSA_TRIGGER + 41 }, held))).toMatchObject({ step: 4, badge: 'FLAT · YOU SOLD' });
    const next = pfsaRead('forming');
    expect(momentOf(inputs({ read: next, now: PFSA_TRIGGER + 600 }, held))?.step).toBe(0);
  });

  it('a plan that is not a trade says so, and no longer speaks of Nova buying it', () => {
    const notTrade = pfsaRead('triggered', { trade: { ok: false, reasons: ['Not a trade: the float is too big'] } });
    const m = momentOf(inputs({ read: notTrade }));
    expect(m).toMatchObject({ badge: 'FIRST PULLBACK · TRIGGERED · NOT A TRADE', tone: 'wait' });
    expect(m?.call).toMatchObject({ title: 'NOT A TRADE', ping: false });
    expect(m?.call?.detail).not.toMatch(/bot|Auto-entry|Approve/);
  });
});

describe('what stands behind each level', () => {
  it('a plan alone is dashed everywhere', () => {
    const lv = orderLevels(inputs({ read: pfsaRead('armed') }));
    expect(lv).toEqual({
      entry: { price: 4.27, behind: 'plan' }, stop: { price: 4.14, behind: 'plan' }, target: { price: 4.52, behind: 'plan' },
      target2: null,                                                  // this plan sells every share at target 1
    });
    expect(level2Markers(lv).map(m => [m.label, m.working])).toEqual([
      ['ENTRY 4.27', false], ['STOP 4.14', false], ['TARGET 4.52', false],
    ]);
  });

  it('shares held turn the entry solid; the stop and target stay the plan\'s', () => {
    // Bought at the trigger: the triggered setup's stop and target judge the shares.
    const i = inputs({ ...HOLDING, last: 4.30 }, remember([{ ...HOLDING, last: 4.30 }]));
    const lv = orderLevels(i);
    expect([lv?.entry?.behind, lv?.stop?.behind, lv?.target?.behind]).toEqual(['held', 'plan', 'plan']);
    expect(level2Markers(lv).map(m => [m.id, m.working])).toEqual([['entry', true], ['stop', false], ['target', false]]);
    const draw = paneDraw(i.read, {
      pane: 'full', layers: { eyes: true, setups: true, levels: false, past: false, labels: 'compact', hidden: [], plan: 'auto' },
      toTime: t => t as never, levels: lv, call: null,
    });
    const byId = Object.fromEntries(draw.lines.map(l => [l.id, l]));
    expect(byId.entry).toMatchObject({ style: 'solid', title: 'ENTRY · held' });
    expect(byId.stop).toMatchObject({ style: 'dashed', title: 'STOP · plan' });
    expect(byId.target).toMatchObject({ style: 'dashed', title: 'TARGET 1 · plan' });
  });

  it('pins the call on its candle', () => {
    const i = inputs();
    const m = momentOf(i);
    const draw = paneDraw(i.read, {
      pane: 'full', layers: { eyes: true, setups: true, levels: false, past: false, labels: 'compact', hidden: [], plan: 'auto' },
      toTime: t => t as never, levels: orderLevels(i), call: m?.call ?? null,
    });
    expect(draw.scene.pins).toEqual([{ t: PFSA_TRIGGER, price: 4.27, label: 'ENTER NOW', color: '#30d158' }]);
  });
});

describe("the plan card's buttons", () => {
  const act = (i: MomentInputs, extra: { bid?: number | null; stageLocked?: string | null } = {}) => planActions({
    moment: momentOf(i), inputs: i, bid: extra.bid ?? 4.50, listening: true, stageLocked: extra.stageLocked ?? null,
    symbol: 'PFSA',
  });

  it('stages the buy, then a sell once you hold: at the target, or at the bid once it is due', () => {
    expect(act(inputs()).map(a => a.id)).toEqual(['stage']);
    const holding = inputs({ ...HOLDING, last: 4.40 }, remember([{ ...HOLDING, last: 4.40 }]));
    expect(act(holding)[0]).toMatchObject({ id: 'stage-sell', label: 'Stage sell 153 @ 4.52', tone: 'plain' });
    const due = remember([{ ...HOLDING, last: 4.40 }, { ...HOLDING, last: 4.52, now: PFSA_TRIGGER + 26 }]);
    expect(act(inputs({ ...HOLDING, last: 4.49 }, due))[0]).toMatchObject({
      label: 'Stage sell 153 @ 4.50', tone: 'target', sell: { qty: 153, price: 4.50 },
    });
  });

  it('a short plan stages the short with its buy stop, and Stage keeps its own lock', () => {
    const short = act(inputs({ read: pfsaRead('armed', { side: 'short' }) }), { stageLocked: 'No plan yet.' })[0];
    expect(short).toMatchObject({ id: 'stage', label: 'Stage short in ticket', locked: 'No plan yet.' });
  });
});

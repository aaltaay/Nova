/**
 * Who trades the stock on the desk (ADR 037): the view's wire, the switch's locks, the moment on the
 * chart (its track, its call and the one ping it keys), the levels with what stands behind them, the
 * Level 2 markers and the plan card's buttons per mode -- on PFSA's first pullback of 2026-09-24.
 */
import { describe, expect, it } from 'vitest';
import { paneDraw } from './chartShapes';
import { momentOf, nextHeld, NO_HELD, type HeldMemory, type MomentInputs } from './momentModel';
import {
  inputs,
  PFSA_SETUP_ID,
  PFSA_TRIGGER,
  pfsaRead,
  pfsaTrade,
  pfsaView,
} from './whoTradesFixtures';
import { level2Markers, modeOf, orderLevels, planActions, sidesOf, switchLock } from './whoTradesModel';
import { normalizeStockMode } from './whoTradesNormalize';

/** Feed the memory a sequence of looks, as the hook does. */
function remember(looks: Partial<MomentInputs>[], start: HeldMemory = NO_HELD): HeldMemory {
  return looks.reduce((held, over) => nextHeld(held, inputs(over, held)), start);
}

const HOLDING = { position: { qty: 153, avgCost: 4.27 } };

describe('the view on the wire', () => {
  it('reads a stock view and keeps what the wire does not say locked', () => {
    const view = normalizeStockMode({
      symbol: 'PFSA', mode: 'auto_entry', buy: 'nova', sell: 'you', venue: 'paper', risk_usd: 20,
      locks: { buy: null, sell: null }, notes: [{ id: 'kill_switch', tone: 'warn', text: 'The kill switch is tripped' }],
      trade: { kind: 'auto_entry', state: 'holding', qty: 153, fill_price: 4.27 }, nova_entries_today: 1,
    });
    expect(view?.mode).toBe('auto_entry');
    expect(view?.locks).toEqual({ buy: null, sell: null });
    expect(view?.trade?.exits).toBe('you');          // a trade that names no seller is the operator's
    expect(view?.notes[0].tone).toBe('warn');
    const noLocks = normalizeStockMode({ symbol: 'PFSA', mode: 'signal', buy: 'you', sell: 'you' });
    expect(noLocks?.locks.buy).toMatch(/could not read/);
    expect(normalizeStockMode({ symbol: 'PFSA', mode: 'yolo', buy: 'you', sell: 'you' })).toBeNull();
  });
});

describe('the switch', () => {
  it('maps the two sides to the four modes and back', () => {
    expect(modeOf('you', 'you')).toBe('signal');
    expect(modeOf('you', 'nova')).toBe('approve');
    expect(modeOf('nova', 'you')).toBe('auto_entry');
    expect(modeOf('nova', 'nova')).toBe('bot');
    expect(sidesOf('approve')).toEqual({ buy: 'you', sell: 'nova' });
  });

  it("locks a Nova side with the view's reason, and Sell to Nova while you hold", () => {
    const live = pfsaView('signal', { venue: 'live', locks: { buy: 'On Live, Nova never buys by itself.', sell: '#604' } });
    const o = { symbol: 'PFSA', held: 0, pending: null };
    expect(switchLock(live, { buy: 'nova', sell: 'you' }, o)).toMatch(/never buys by itself/);
    expect(switchLock(live, { buy: 'you', sell: 'you' }, o)).toBeNull();
    expect(switchLock(pfsaView('signal'), { buy: 'you', sell: 'nova' }, { ...o, held: 153 })).toMatch(/You hold PFSA/);
    expect(switchLock(null, { buy: 'you', sell: 'you' }, o)).toMatch(/Reading who trades PFSA/);
    expect(switchLock(pfsaView('signal'), { buy: 'nova', sell: 'you' }, { ...o, pending: 'Saving…' })).toBe('Saving…');
  });
});

describe('the moment on the chart', () => {
  it('forming: the badge says how near, and Signal only says get ready', () => {
    const m = momentOf(inputs({ read: pfsaRead('near'), now: PFSA_TRIGGER - 2 }));
    expect(m).toMatchObject({ step: 0, tone: 'near', badge: 'FIRST PULLBACK · NEAR 0.03', exitLabel: 'Your exit' });
    expect(m?.call).toMatchObject({ title: 'GET READY', ping: false });
    expect(m?.call?.detail).toMatch(/Enter above 4.26/);
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
    expect(due?.call).toMatchObject({ id: `sell-target:${held.since}`, title: 'SELL NOW · TARGET 4.52', ping: true });
    expect(due?.call?.detail).toMatch(/No order is working: the exit is yours/);
  });

  it("a setup that triggers minutes into a hand trade does not lend it its stop and target", () => {
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

  it('Approve: approved before the trigger, sent, bought, then sold at the target', () => {
    const approval = { setup_id: PFSA_SETUP_ID, setup_type: 'first_pullback', entry: 4.27, stop: 4.14, target: 4.52,
      qty: 153, approved_at: PFSA_TRIGGER - 60, state: 'waiting' as const, reason: null };
    const waiting = momentOf(inputs({ read: pfsaRead('armed'), who: pfsaView('approve', { approval }) }));
    expect(waiting).toMatchObject({ step: 0, exitLabel: 'Target / stop' });
    expect(waiting?.call?.detail).toMatch(/Nova sends buy 153 @ 4.27 with stop 4.14 and target 4.52 when 4.26 prints/);

    const sent = momentOf(inputs({ who: pfsaView('approve', { trade: pfsaTrade('approve', 'entering') }) }));
    expect(sent).toMatchObject({ step: 1, badge: 'SENT · BUY 153 @ 4.27' });

    const bought = momentOf(inputs({ who: pfsaView('approve', { trade: pfsaTrade('approve', 'holding') }), last: 4.30 }));
    expect(bought).toMatchObject({ step: 2, badge: 'IN THE TRADE · +$4.59', exitLabel: 'Target / stop' });
    expect(bought?.call).toMatchObject({ title: 'BOUGHT 153 @ 4.27', ping: true, pin: { label: 'BOUGHT', at: PFSA_TRIGGER + 0.5 } });

    const closed = pfsaTrade('approve', 'closed', { exit_price: 4.52, exit_reason: 'target', closed_at: PFSA_TRIGGER + 26 });
    const sold = momentOf(inputs({ who: pfsaView('approve', { trade: closed }), now: PFSA_TRIGGER + 30 }));
    expect(sold).toMatchObject({ step: 3, tone: 'done', badge: 'SOLD 4.52 · +$38.25' });
    expect(sold?.call).toMatchObject({ ping: true, pin: { label: 'SOLD 4.52', price: 4.52 } });
    const later = momentOf(inputs({ who: pfsaView('approve', { trade: closed }), now: PFSA_TRIGGER + 120 }));
    expect(later).toMatchObject({ step: 4, badge: 'FLAT · +$38.25', call: null });
  });

  it('Auto-entry: Nova bought, and the target is yours to sell -- Nova will not', () => {
    const who = pfsaView('auto_entry', { trade: pfsaTrade('auto_entry', 'holding') });
    const m = momentOf(inputs({ who, last: 4.30 }));
    expect(m?.call).toMatchObject({ title: 'NOVA BOUGHT 153 @ 4.27' });
    expect(m?.call?.detail).toBe('No stop or target is working. The exit is yours.');
    const held = remember([{ who, last: 4.30 }, { who, last: 4.53, now: PFSA_TRIGGER + 26 }]);
    expect(momentOf(inputs({ who, last: 4.53, now: PFSA_TRIGGER + 26 }, held))?.call?.detail)
      .toMatch(/Nova will not sell: the exit is yours/);
  });

  it('the bot selling says so, and a missed entry is not an event to ping', () => {
    const exiting = pfsaTrade('bot', 'holding', { exiting: true });
    expect(momentOf(inputs({ who: pfsaView('bot', { trade: exiting }) }))?.badge).toBe('NOVA IS SELLING');
    const missed = pfsaTrade('auto_entry', 'missed', { closed_at: PFSA_TRIGGER + 10 });
    const m = momentOf(inputs({ who: pfsaView('auto_entry', { trade: missed }), now: PFSA_TRIGGER + 12 }));
    expect(m).toMatchObject({ badge: "NOVA'S BUY MISSED" });
    expect(m?.call?.ping).toBe(false);
  });
});

describe('what stands behind each level', () => {
  it('a plan alone is dashed everywhere', () => {
    const lv = orderLevels(inputs({ read: pfsaRead('armed') }));
    expect(lv).toEqual({
      entry: { price: 4.27, behind: 'plan' }, stop: { price: 4.14, behind: 'plan' }, target: { price: 4.52, behind: 'plan' },
    });
    expect(level2Markers(lv).map(m => [m.label, m.working])).toEqual([
      ['ENTRY 4.27', false], ['STOP 4.14', false], ['TARGET 4.52', false],
    ]);
  });

  it("Approve's bracket stands behind all three; the bot's target rests and its stop is watched", () => {
    const approve = orderLevels(inputs({ who: pfsaView('approve', { trade: pfsaTrade('approve', 'entering') }) }));
    expect([approve?.entry?.behind, approve?.stop?.behind, approve?.target?.behind]).toEqual(['order', 'order', 'order']);
    const bot = orderLevels(inputs({ who: pfsaView('bot', { trade: pfsaTrade('bot', 'holding') }) }));
    expect([bot?.entry?.behind, bot?.stop?.behind, bot?.target?.behind]).toEqual(['held', 'watched', 'order']);
    const taken = orderLevels(inputs({ who: pfsaView('signal', { trade: pfsaTrade('approve', 'holding', { exits: 'you' }) }) }));
    expect([taken?.stop?.behind, taken?.target?.behind]).toEqual(['plan', 'plan']);
  });

  it('draws orders solid on the chart and pins the call on its candle', () => {
    const i = inputs({ who: pfsaView('approve', { trade: pfsaTrade('approve', 'holding') }), last: 4.30 });
    const m = momentOf(i);
    const draw = paneDraw(i.read, {
      pane: 'full', layers: { setups: true, levels: false, hidden: [], plan: 'auto' }, toTime: t => t as never,
      levels: orderLevels(i), call: m?.call ?? null,
    });
    const byId = Object.fromEntries(draw.lines.map(l => [l.id, l]));
    expect(byId.stop).toMatchObject({ style: 'solid', title: 'STOP · order' });
    expect(byId.target).toMatchObject({ style: 'solid', title: 'TARGET · order' });
    expect(byId.entry).toMatchObject({ style: 'solid', title: 'ENTRY · held' });
    expect(draw.scene.pins).toEqual([{ t: PFSA_TRIGGER + 0.5, price: 4.27, label: 'BOUGHT', color: '#0a84ff' }]);
  });
});

describe("the plan card's buttons", () => {
  const act = (i: MomentInputs, extra: { bid?: number | null; stageLocked?: string | null } = {}) => planActions({
    moment: momentOf(i), inputs: i, bid: extra.bid ?? 4.50, listening: true, stageLocked: extra.stageLocked ?? null,
    symbol: 'PFSA',
  });

  it('Signal only stages the buy, then a sell once you hold: at the target, or at the bid once it is due', () => {
    expect(act(inputs()).actions.map(a => a.id)).toEqual(['stage']);
    const holding = inputs({ ...HOLDING, last: 4.40 }, remember([{ ...HOLDING, last: 4.40 }]));
    expect(act(holding).actions[0]).toMatchObject({ id: 'stage-sell', label: 'Stage sell 153 @ 4.52', tone: 'plain' });
    const due = remember([{ ...HOLDING, last: 4.40 }, { ...HOLDING, last: 4.52, now: PFSA_TRIGGER + 26 }]);
    expect(act(inputs({ ...HOLDING, last: 4.49 }, due)).actions[0]).toMatchObject({
      label: 'Stage sell 153 @ 4.50', tone: 'target', sell: { qty: 153, price: 4.50 },
    });
  });

  it('Approve: approve an armed plan, buy now after its trigger, never while it only forms', () => {
    const armed = act(inputs({ read: pfsaRead('armed'), who: pfsaView('approve') })).actions[0];
    expect(armed).toMatchObject({ id: 'approve', label: 'Approve 153 @ 4.27', locked: null });
    const forming = act(inputs({ read: pfsaRead('forming'), who: pfsaView('approve') })).actions[0];
    expect(forming.locked).toMatch(/has not armed/);
    expect(act(inputs({ who: pfsaView('approve') })).actions[0]).toMatchObject({ id: 'approve-now', label: 'Approve: buy 153 now' });
    const approval = { setup_id: PFSA_SETUP_ID, setup_type: null, entry: 4.27, stop: 4.14, target: 4.52, qty: 153,
      approved_at: PFSA_TRIGGER - 5, state: 'waiting' as const, reason: null };
    expect(act(inputs({ read: pfsaRead('armed'), who: pfsaView('approve', { approval }) })).actions[0].id)
      .toBe('cancel-approval');
  });

  it('whoever holds the exits: cancel the bracket, or take over from the bot', () => {
    const approve = act(inputs({ who: pfsaView('approve', { trade: pfsaTrade('approve', 'holding') }) })).actions;
    expect(approve).toMatchObject([{ id: 'take-over', label: 'Cancel stop and target' }]);
    const bot = act(inputs({ who: pfsaView('bot', { trade: pfsaTrade('bot', 'holding') }) })).actions;
    expect(bot).toMatchObject([{ id: 'take-over', label: 'Take over the exit' }]);
  });

  it('Auto-entry and the bot turn off, and a closed trade says how it went', () => {
    expect(act(inputs({ read: pfsaRead('armed'), who: pfsaView('auto_entry') })).actions[0].id).toBe('auto-off');
    expect(act(inputs({ read: pfsaRead('armed'), who: pfsaView('bot') })).actions[0]).toMatchObject({
      id: 'bot-off', label: 'Bot on PFSA · stop it',
    });
    const closed = pfsaTrade('approve', 'closed', { exit_price: 4.52, exit_reason: 'target', closed_at: PFSA_TRIGGER + 26 });
    const done = act(inputs({ who: pfsaView('approve', { trade: closed }), now: PFSA_TRIGGER + 200 }));
    expect(done).toEqual({ actions: [], status: 'Closed · +$38.25' });
  });
});

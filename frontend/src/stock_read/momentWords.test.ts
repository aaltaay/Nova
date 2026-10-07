/**
 * A short setup's plan before the trade (ADR 049): the badge names it ▼ SHORT, the call says SHORT NOW under the
 * trigger, the track reads Short, and every Nova mode trades it as it trades a long (#778 step 5): Approve sends it
 * with its buy stop and cover, Auto-entry and the bot short it with its buy stop.
 */
import { describe, expect, it } from 'vitest';
import { planBadgeText } from './chartShapes';
import { momentOf, type MomentInputs } from './momentModel';
import type { StockPlan, StockRead } from './types';
import { BOT_READY, inputs, pfsaRead, pfsaView } from './whoTradesFixtures';

const SHORT: Partial<StockPlan> = {
  side: 'short', setup_type: 'bear_flag', kind: 'bear_flag', trigger: 4.26, entry: 4.25, stop: 4.38, target: 3.99,
  risk: 0.13, reward: 0.26,
};

function shortRead(state: StockPlan['state'], distance: number | null = 0.03): StockRead {
  const read = pfsaRead(state, SHORT, distance);
  return { ...read, setups: read.setups.map(l => ({ ...l, setup_type: 'bear_flag', side: 'short' as const })) };
}

const at = (over: Partial<MomentInputs>) => momentOf(inputs(over));

describe('a short setup\'s plan before the trade', () => {
  it('names the setup ▼ SHORT on the badge and reads the short\'s track', () => {
    const m = at({ read: shortRead('near'), last: 4.29 });
    expect(m?.badge).toMatch(/^BEAR FLAG ▼ SHORT · /);
    expect(m?.side).toBe('short');
    expect(planBadgeText(shortRead('armed'))).toBe('BEAR FLAG ▼ SHORT · ARMED');
  });

  it('gets ready over the trigger and calls SHORT NOW when it prints under it with the tape at go', () => {
    const near = at({ read: shortRead('near'), last: 4.29 });
    expect(near?.call?.title).toBe('GET READY');
    expect(near?.call?.detail).toMatch(/over the trigger\. Short under 4\.26: the chart says SHORT NOW when it prints\./);
    const now = at({ read: shortRead('triggered'), last: 4.25 });
    expect(now?.call?.title).toBe('SHORT NOW · 4.25');
    expect(now?.call?.detail).toMatch(/Your click: stage the short with its buy stop\./);
    expect(now?.call?.pin?.label).toBe('SHORT NOW');
  });

  it('Approve sends the short with its buy stop and cover, and the approval says what it will send', () => {
    const m = at({ read: shortRead('near'), last: 4.29, who: pfsaView('approve') });
    expect(m?.call?.title).toBe('APPROVE TO SEND');
    expect(m?.call?.detail).toMatch(/^Approve the plan and Nova sends short \S+ @ 4\.25 with its buy stop and cover at the trigger\.$/);
    const approval = { setup_id: 'S1', setup_type: 'bear_flag', entry: 4.25, stop: 4.38, target: 3.99, qty: 7,
      approved_at: 0, state: 'waiting' as const, reason: null };
    const waiting = at({ read: shortRead('near'), last: 4.29, who: pfsaView('approve', { approval }) });
    expect(waiting?.call).toMatchObject({ title: 'APPROVED', detail: 'Nova sends short 7 @ 4.25 with buy stop 4.38 and '
      + 'cover 3.99 when 4.26 prints with the tape at go.' });
    const now = at({ read: shortRead('triggered'), last: 4.25, who: pfsaView('approve') });
    expect(now?.call?.detail).toMatch(/Approve: short \S+ now sends it with its buy stop and cover\.$/);
  });

  it('Auto-entry and the bot short it at the trigger, with its buy stop, when nothing blocks', () => {
    const size = { qty: 10, by_risk: 153, capped_by: 'max_shares', text: null };
    const auto = at({ read: shortRead('near'), last: 4.29,
      who: pfsaView('auto_entry', { size, bot: { ...BOT_READY, on_list: false } }) });
    expect(auto?.call?.title).toBe('BOT SHORTS AT 4.26');
    expect(auto?.call?.detail).toMatch(/the bot shorts 10 with its buy stop 4\.38\. Every cover is yours\.$/);
    const bot = at({ read: shortRead('near'), last: 4.29, who: pfsaView('bot') });
    expect(bot?.call?.title).toBe('THE BOT TRADES THIS');
    expect(bot?.call?.detail).toMatch(/It shorts at the trigger and covers at 3\.99, at its buy stop 4\.38 or after 15 minutes\.$/);
    // Blocked: it says the short.
    const blocked = at({ read: shortRead('near'), last: 4.29,
      who: pfsaView('auto_entry', { notes: [{ id: 'window', tone: 'warn', text: 'The bot window is closed.' }] }) });
    expect(blocked?.call?.title).toBe('THE BOT WILL NOT SHORT THIS');
  });
});

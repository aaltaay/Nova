import { describe, expect, it } from 'vitest';
import type { StockModeView } from './types';
import { whoAnswer } from './whoAnswer';

const view = (over: Partial<StockModeView>): StockModeView => ({
  schema_version: 1, symbol: 'AISP', generated_at: 0, venue: 'paper', mode: 'bot', buy: 'nova', sell: 'nova',
  risk_usd: 20, set_at: null, locks: { buy: null, sell: null }, notes: [], approval: null, trade: null,
  entries_today: { count: 0, cap: 1 }, nova_entries_today: 0, size: null, last_event: null, bot: null, ...over,
} as unknown as StockModeView);

describe('the stock\'s own answer (ADR 043)', () => {
  it('says no while the stock is off the hot list, whatever its switch', () => {
    expect(whoAnswer('AISP', false, view({}))).toEqual({ tone: 'no', text: 'Nova may buy AISP: no · not on today\'s hot list' });
  });

  it('says you buy it when Buy is You', () => {
    expect(whoAnswer('AISP', true, view({ buy: 'you', mode: 'signal' }))?.text).toBe('Nova may buy AISP: no · you buy it');
  });

  it('names the first thing that keeps Nova from acting, and how many more', () => {
    const notes = [
      { id: 'bot_trip', tone: 'warn', text: 'the bot trip fired at 09:43' },
      { id: 'window', tone: 'warn', text: 'the bot window closed at 10:00' },
      { id: 'info', tone: 'info', text: 'an info line' },
    ];
    expect(whoAnswer('AISP', true, view({ notes } as Partial<StockModeView>))?.text)
      .toBe('Nova may buy AISP: no · the bot trip fired at 09:43 (and 1 more below)');
  });

  it('says yes only when listed, Buy is Nova and nothing stands in the way', () => {
    expect(whoAnswer('AISP', true, view({}))).toEqual({ tone: 'yes', text: 'Nova may buy AISP: yes, at its next go trigger' });
    expect(whoAnswer('AISP', null, view({}))).toBeNull();     // the list not read yet: no claim
    expect(whoAnswer('AISP', true, null)).toBeNull();
  });
});

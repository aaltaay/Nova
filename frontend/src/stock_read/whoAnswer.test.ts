import { describe, expect, it } from 'vitest';
import type { StockModeView } from './types';
import { whoAnswer } from './whoAnswer';

const view = (over: Partial<StockModeView>): StockModeView => ({
  schema_version: 1, symbol: 'AISP', generated_at: 0, venue: 'paper', mode: 'bot', buy: 'nova', sell: 'nova',
  risk_usd: 20, set_at: null, locks: { buy: null, sell: null }, notes: [], approval: null, trade: null,
  entries_today: { count: 0, cap: 1 }, nova_entries_today: 0, size: null, last_event: null, bot: null, ...over,
} as unknown as StockModeView);

describe('the stock\'s own answer (ADR 044, amended 2026-10-06: the hot list is no part of it)', () => {
  it('says you buy it when Buy is You', () => {
    expect(whoAnswer('AISP', view({ buy: 'you', mode: 'signal' }))).toEqual({ tone: 'you', text: 'Bot may buy AISP: no · you buy it' });
  });

  it('names the first thing that keeps the bot from acting, and how many more', () => {
    const notes = [
      { id: 'bot_trip', tone: 'warn', text: 'the bot trip fired at 09:43' },
      { id: 'window', tone: 'warn', text: 'the bot window closed at 10:00' },
      { id: 'info', tone: 'info', text: 'an info line' },
    ];
    expect(whoAnswer('AISP', view({ notes } as Partial<StockModeView>))?.text)
      .toBe('Bot may buy AISP: no · the bot trip fired at 09:43 (and 1 more below)');
  });

  it('says yes when Buy is Bot and nothing stands in the way, starred or not', () => {
    expect(whoAnswer('AISP', view({}))).toEqual({ tone: 'yes', text: 'Bot may buy AISP: yes, at its next go trigger' });
    expect(whoAnswer('AISP', null)).toBeNull();
  });
});

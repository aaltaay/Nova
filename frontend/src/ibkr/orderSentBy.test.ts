import { describe, expect, it } from 'vitest';
import { orderSentBy } from './orderSentBy';

describe('orderSentBy (operator report 2026-10-01: "I don\'t remember selling it")', () => {
  it('names the loss breaker that sold, not just "a flatten"', () => {
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'bot_trip' })).toMatchObject({
      label: 'Bot trip',
      tone: 'breaker',
    });
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'all_stop' }).label).toBe('All-stop');
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'emergency_kill' }).label).toBe('KILL');
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'bot_trip' }).tip).toMatch(/Bots page/);
  });

  it('tells your own orders from Nova\'s', () => {
    expect(orderSentBy({ order_source: 'manual', order_origin: null })).toMatchObject({ label: 'You', tone: 'you' });
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'ticket_flatten' }).label).toBe('You · Flatten');
    expect(orderSentBy({ order_source: 'manual', order_origin: 'approve' })).toMatchObject({
      label: 'Approve',
      tone: 'nova',
    });
    expect(orderSentBy({ order_source: 'bot', order_origin: 'auto_entry' }).label).toBe('Auto-entry');
    expect(orderSentBy({ order_source: 'bot', order_origin: 'bot' }).label).toBe('Bot');
    expect(orderSentBy({ order_source: 'bot', order_origin: 'bot_api' }).label).toBe('Bot API');
  });

  it('says an old flatten could be any of them, never guessing which', () => {
    const by = orderSentBy({ order_source: 'flatten', order_origin: null });
    expect(by).toMatchObject({ label: 'Flatten', tone: 'unknown' });
    expect(by.tip).toMatch(/KILL/);
    expect(by.tip).toMatch(/loss breaker/);
  });

  it('marks orders placed outside Nova, and rows with no sender recorded', () => {
    expect(orderSentBy({ source: 'ib_recovered', order_source: null }).label).toBe('Outside Nova');
    expect(orderSentBy({ source: 'nova' })).toMatchObject({ label: '—', tone: 'unknown' });
    expect(orderSentBy({}).tip).toMatch(/Not recorded/);
  });

  it('shows an origin this desk does not know as it is', () => {
    expect(orderSentBy({ order_source: 'bot', order_origin: 'new_thing' })).toMatchObject({
      label: 'new_thing',
      tone: 'unknown',
    });
  });
});

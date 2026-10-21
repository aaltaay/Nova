import { describe, expect, it } from 'vitest';
import { orderSentBy } from './orderSentBy';

describe('orderSentBy (operator report 2026-10-01: "I don\'t remember selling it")', () => {
  it('names the loss rule that sold, not just "a flatten"', () => {
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'bot_trip' })).toMatchObject({
      label: 'Bot trip',
      tone: 'breaker',
    });
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'all_stop' }).label).toBe('All-stop');
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'emergency_kill' }).label).toBe('KILL');
    // Rows from before ADR 056 keep their names; their tips point at where the one limit is set now.
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'bot_trip' }).tip).toMatch(/Settings > Loss limits/);
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'bot_trip' }).tip).not.toMatch(/Bots page/);
  });

  it('names the daily loss limit\'s Auto sell (ADR 056)', () => {
    const by = orderSentBy({ order_source: 'flatten', order_origin: 'loss_limit' });
    expect(by).toMatchObject({ label: 'Loss limit', tone: 'breaker' });
    expect(by.tip).toMatch(/Settings > Loss limits/);
  });

  it('names which loss line sold: yours or the bots\' (ADR 061)', () => {
    expect(orderSentBy({ order_source: 'flatten', order_origin: 'loss_limit_you' })).toMatchObject({
      label: 'Loss limit · You', tone: 'breaker' });
    const bots = orderSentBy({ order_source: 'flatten', order_origin: 'loss_limit_bots' });
    expect(bots).toMatchObject({ label: 'Loss limit · Bots', tone: 'breaker' });
    expect(bots.tip).toMatch(/Your shares were left alone/);
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
    expect(by.tip).toMatch(/daily loss/);
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

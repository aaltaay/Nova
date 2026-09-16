/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import * as prefill from '../ibkr/orderTicketPrefill';
import { adviseTicketPrefill, stageAdviseTicket } from './ticketFromStance';

describe('advise ticket prefill', () => {
  it('maps LONG to BUY and never marks places', () => {
    const ticket = adviseTicketPrefill('aapl', {
      stance: 'LONG',
      reasons: [],
      risks: [],
      ticket: {
        symbol: 'AAPL',
        side: 'BUY',
        order_type: 'MKT',
        quantity_value: '25',
        limit_price: '',
        places: false,
      },
    });
    expect(ticket).toEqual({
      symbol: 'AAPL',
      side: 'BUY',
      orderType: 'MKT',
      quantityValue: '25',
      limitPrice: '',
    });
  });

  it('stages through the ticket channel and never places', () => {
    const spy = vi.spyOn(prefill, 'requestOrderTicketPrefill');
    const staged = stageAdviseTicket({
      symbol: 'NVDA',
      side: 'SELL',
      order_type: 'MKT',
      quantity_value: '10',
      limit_price: '',
      places: false,
    });
    expect(spy).toHaveBeenCalledWith(staged);
    expect(staged?.side).toBe('SELL');
  });

  it('refuses a ticket marked places:true', () => {
    const ticket = adviseTicketPrefill('AAPL', {
      stance: 'LONG',
      reasons: [],
      risks: [],
      ticket: {
        symbol: 'AAPL',
        side: 'BUY',
        order_type: 'MKT',
        quantity_value: '1',
        limit_price: '',
        places: true as unknown as false,
      },
    });
    expect(ticket).toBeNull();
  });
});

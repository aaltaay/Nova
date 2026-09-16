import { describe, expect, it } from 'vitest';
import {
  TICKER_TRADE_LABEL_BUY,
  TICKER_TRADE_LABEL_SELL,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import {
  allowShortSide,
  clampTicketSide,
  orderSideToTicketSide,
  placeActionLabel,
  ticketSideOptions,
  ticketSideToOrder,
} from './ticketSide';
import type { IbkrAccountSummary } from './types';

function summary(overrides: Partial<IbkrAccountSummary> = {}): IbkrAccountSummary {
  return {
    connected: true,
    mode: 'paper',
    NetLiquidation: 1000,
    BuyingPower: 50_000,
    ...overrides,
  };
}

describe('ticketSideOptions', () => {
  it('shows Buy/Sell/Short only on Margin', () => {
    expect(ticketSideOptions('margin')).toEqual(['buy', 'sell', 'short']);
  });

  it('hides Short on Cash and Unknown -- never invents Margin', () => {
    expect(ticketSideOptions('cash')).toEqual(['buy', 'sell']);
    expect(ticketSideOptions('unknown')).toEqual(['buy', 'sell']);
  });
});

describe('allowShortSide', () => {
  it('allows Short only when AccountType is a Margin token', () => {
    expect(allowShortSide(summary({ AccountType: 'MARGIN' }))).toBe(true);
    expect(allowShortSide(summary({ AccountType: 'CASH' }))).toBe(false);
  });

  it('does not invent Margin from BuyingPower or INDIVIDUAL', () => {
    expect(allowShortSide(summary({ BuyingPower: 50_000 }))).toBe(false);
    expect(allowShortSide(summary({ AccountType: 'INDIVIDUAL' }))).toBe(false);
    expect(allowShortSide(null)).toBe(false);
    expect(allowShortSide(summary({ connected: false, AccountType: 'MARGIN' }))).toBe(
      false,
    );
  });
});

describe('ticketSideToOrder', () => {
  it('maps Buy to BUY without short_entry', () => {
    expect(ticketSideToOrder('buy')).toEqual({ side: 'BUY', shortEntry: false });
  });

  it('maps Sell to SELL without short_entry -- close long only', () => {
    expect(ticketSideToOrder('sell')).toEqual({ side: 'SELL', shortEntry: false });
  });

  it('maps Short to SELL + short_entry', () => {
    expect(ticketSideToOrder('short')).toEqual({ side: 'SELL', shortEntry: true });
  });
});

describe('placeActionLabel', () => {
  it('follows the selected Side', () => {
    expect(placeActionLabel('buy', 'nvda')).toBe(`${TICKER_TRADE_LABEL_BUY} NVDA`);
    expect(placeActionLabel('sell', 'nvda')).toBe(`${TICKER_TRADE_LABEL_SELL} NVDA`);
    expect(placeActionLabel('short', 'nvda')).toBe(`${TICKER_TRADE_LABEL_SHORT} NVDA`);
  });
});

describe('clampTicketSide', () => {
  it('drops Short to Sell when Short is not allowed', () => {
    expect(clampTicketSide('short', false)).toBe('sell');
    expect(clampTicketSide('short', true)).toBe('short');
    expect(clampTicketSide('buy', false)).toBe('buy');
  });
});

describe('orderSideToTicketSide', () => {
  it('maps broker sides to Buy/Sell -- never Short', () => {
    expect(orderSideToTicketSide('BUY')).toBe('buy');
    expect(orderSideToTicketSide('SELL')).toBe('sell');
  });
});

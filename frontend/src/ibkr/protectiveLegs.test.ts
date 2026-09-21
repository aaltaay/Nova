/**
 * #91 — the ticket's default protective legs: when they attach, when they are
 * skipped, and when the ticket refuses rather than send a naked entry.
 */
import { describe, expect, it } from 'vitest';
import {
  TICKET_LEGS_EXIT_NOTE,
  TICKET_LEGS_LIMIT_ONLY_ERROR,
  TICKET_LEGS_NO_PRICE_ERROR,
  TICKET_LEGS_OFFSET_ERROR,
  TICKET_LEGS_SIM_NOTE,
} from '../constantGroups/trade_defaults';
import { defaultTradeDefaultsPrefs } from '../settings/tradeDefaultsPrefs';
import { planProtectiveLegs, roundToTick } from './protectiveLegs';
import type { ProtectiveLegsInput } from './protectiveLegs';

function input(over: Partial<ProtectiveLegsInput> = {}): ProtectiveLegsInput {
  return {
    prefs: {
      ...defaultTradeDefaultsPrefs(),
      protectiveLegs: true,
      takeProfitPct: 2,
      stopLossPct: 1,
    },
    side: 'BUY',
    shortEntry: false,
    orderType: 'LMT',
    limitPrice: 10,
    positionQty: null,
    mode: 'paper',
    ...over,
  };
}

describe('planProtectiveLegs', () => {
  it('does nothing at all while the defaults are off', () => {
    const plan = planProtectiveLegs(
      input({ prefs: defaultTradeDefaultsPrefs() }),
    );
    expect(plan).toEqual({ kind: 'none', note: null });
  });

  it('brackets a long limit entry above and below the entry', () => {
    const plan = planProtectiveLegs(input());
    expect(plan).toMatchObject({
      kind: 'attach',
      takeProfitPrice: 10.2,
      stopLossPrice: 9.9,
    });
  });

  it('mirrors the legs for a short entry', () => {
    const plan = planProtectiveLegs(
      input({ side: 'SELL', shortEntry: true }),
    );
    expect(plan).toMatchObject({
      kind: 'attach',
      takeProfitPrice: 9.8,
      stopLossPrice: 10.1,
    });
  });

  it('never legs an exit: a closing sell or a cover', () => {
    expect(planProtectiveLegs(input({ side: 'SELL' }))).toEqual({
      kind: 'none',
      note: TICKET_LEGS_EXIT_NOTE,
    });
    expect(planProtectiveLegs(input({ positionQty: -100 }))).toEqual({
      kind: 'none',
      note: TICKET_LEGS_EXIT_NOTE,
    });
  });

  it('skips legs in Sim, which has no brackets', () => {
    expect(planProtectiveLegs(input({ mode: 'sim' }))).toEqual({
      kind: 'none',
      note: TICKET_LEGS_SIM_NOTE,
    });
  });

  it('refuses a non-limit entry instead of sending it unprotected', () => {
    for (const orderType of ['MKT', 'STP', 'STP LMT', 'TRAIL'] as const) {
      expect(planProtectiveLegs(input({ orderType }))).toEqual({
        kind: 'refuse',
        error: TICKET_LEGS_LIMIT_ONLY_ERROR,
      });
    }
    expect(planProtectiveLegs(input({ limitPrice: null }))).toEqual({
      kind: 'refuse',
      error: TICKET_LEGS_NO_PRICE_ERROR,
    });
  });

  it('refuses offsets that round onto the entry price', () => {
    const plan = planProtectiveLegs(
      input({
        limitPrice: 10,
        prefs: {
          ...defaultTradeDefaultsPrefs(),
          protectiveLegs: true,
          takeProfitPct: 0.01,
          stopLossPct: 0.01,
        },
      }),
    );
    expect(plan).toEqual({ kind: 'refuse', error: TICKET_LEGS_OFFSET_ERROR });
  });

  it('rounds to the IBKR tick on each side of a dollar', () => {
    expect(roundToTick(10.23456)).toBe(10.23);
    expect(roundToTick(0.123456)).toBe(0.1235);
    const subDollar = planProtectiveLegs(
      input({
        limitPrice: 0.5,
        prefs: {
          ...defaultTradeDefaultsPrefs(),
          protectiveLegs: true,
          takeProfitPct: 10,
          stopLossPct: 5,
        },
      }),
    );
    expect(subDollar).toMatchObject({
      kind: 'attach',
      takeProfitPrice: 0.55,
      stopLossPrice: 0.475,
    });
  });
});

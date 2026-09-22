/**
 * The compact ticket's header and cost line, off the ticket component: the
 * TIF the next order carries (#91: a Settings > Trade pref, written by the
 * header's DAY | GTC so what is shown is what is sent), the `Cost · BP after`
 * estimate from the same sizing the Place path runs, and whether this venue
 * estimates its fills.
 *
 * The caller hands in the price the venue trades at -- on Sim off the live
 * edge that is the replay's at the playhead (`useReplayQuote`), null with a
 * `priceNote` when there is none, so a Market order is never priced from a
 * live last the quote card does not show (QA 2026-09-22, V24 / R10).
 */
import { useState } from 'react';
import type { TradeDefaultTif } from '../constantGroups/trade_defaults';
import {
  readTradeDefaultsPrefs,
  writeTradeDefaultsPrefs,
} from '../settings/tradeDefaultsPrefs';
import type { ManualOrderSide, ManualOrderType, QuantityMode } from './orderEntry';
import { estimateTicketCost, type TicketCostEstimate } from './ticketCost';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

interface Params {
  symbol: string;
  mode: IbkrMode;
  side: ManualOrderSide;
  shortEntry: boolean;
  orderType: ManualOrderType;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
  referencePrice: number | null;
  summary: IbkrAccountSummary | null;
  position: IbkrPosition | null;
  /** Why the venue has no market price right now, when it has none (Sim off the edge). */
  priceNote?: string | null;
}

export function useCompactTicket(p: Params): {
  tif: TradeDefaultTif;
  selectTif: (next: TradeDefaultTif) => void;
  cost: TicketCostEstimate;
  practice: boolean;
} {
  const [tif, setTif] = useState<TradeDefaultTif>(() => readTradeDefaultsPrefs().tif);

  function selectTif(next: TradeDefaultTif) {
    writeTradeDefaultsPrefs({ ...readTradeDefaultsPrefs(), tif: next });
    setTif(next);
  }

  const practice = p.mode === 'paper' || p.mode === 'sim';
  const cost = estimateTicketCost(
    {
      symbol: p.symbol,
      side: p.side,
      orderType: p.orderType,
      quantityMode: p.quantityMode,
      quantityValue: p.quantityValue,
      limitPrice: p.limitPrice,
      stopPrice: p.stopPrice,
      outsideRth: p.outsideRth,
      shortEntry: p.shortEntry,
    },
    {
      marketReferencePrice: p.referencePrice,
      buyingPower: p.summary?.BuyingPower ?? null,
      positionQty: p.position?.qty ?? null,
    },
    undefined,
    { practice, priceNote: p.priceNote ?? null },
  );

  return { tif, selectTif, cost, practice };
}

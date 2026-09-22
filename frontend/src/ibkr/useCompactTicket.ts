/**
 * The compact ticket's header and cost line, off the ticket component: the
 * TIF the next order carries (#91: a Settings > Trade pref, written by the
 * header's DAY | GTC so what is shown is what is sent), the `Cost · BP after`
 * estimate from the same sizing the Place path runs, and whether this venue
 * estimates its fills.
 *
 * On Sim the tab's market reference is trusted only when the tab can fill:
 * this symbol's replay is loaded, or the desk is at the live edge. Otherwise a
 * Market order would be priced from a live last the quote card does not show
 * (QA 2026-09-22, V24) -- the line is a dash with the reason instead.
 */
import { useState } from 'react';
import { TICKET_COST_NO_SIM_PRICE } from '../constantGroups/trader_chrome';
import type { TradeDefaultTif } from '../constantGroups/trade_defaults';
import {
  readTradeDefaultsPrefs,
  writeTradeDefaultsPrefs,
} from '../settings/tradeDefaultsPrefs';
import { useSimReplayTarget } from '../sim/useSimReplayTarget';
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
}

export function useCompactTicket(p: Params): {
  tif: TradeDefaultTif;
  selectTif: (next: TradeDefaultTif) => void;
  cost: TicketCostEstimate;
  practice: boolean;
} {
  const [tif, setTif] = useState<TradeDefaultTif>(() => readTradeDefaultsPrefs().tif);
  const { clock, target } = useSimReplayTarget(p.symbol);

  function selectTif(next: TradeDefaultTif) {
    writeTradeDefaultsPrefs({ ...readTradeDefaultsPrefs(), tif: next });
    setTif(next);
  }

  const practice = p.mode === 'paper' || p.mode === 'sim';
  // Sim: no clock yet is unknown, not trusted; the edge and this symbol's replay are.
  const simPriceTrusted = p.mode !== 'sim'
    || (clock != null && (target.kind === 'ok' || target.kind === 'live-edge'));
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
      marketReferencePrice: simPriceTrusted ? p.referencePrice : null,
      buyingPower: p.summary?.BuyingPower ?? null,
      positionQty: p.position?.qty ?? null,
    },
    undefined,
    { practice, priceNote: simPriceTrusted ? null : TICKET_COST_NO_SIM_PRICE },
  );

  return { tif, selectTif, cost, practice };
}

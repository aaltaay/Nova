/**
 * Honest Working-row copy when a MKT cannot fill until the open.
 */
import type { MarketSessionKind } from '../chart/sessionHighlight';
import { remainingShares } from './orderQtyMath';
import type { IbkrOrder } from './types';

export function workingOrderStatusDisplay(
  order: IbkrOrder,
  statusLabel: string,
  sessionKind: MarketSessionKind,
): { label: string; title: string } {
  if (order.held_until) {
    return {
      label: `${statusLabel} (held to open)`,
      title: `${order.status} -- held until ${order.held_until} (exchange open)`,
    };
  }
  const rem = remainingShares(order);
  const isMkt = order.order_type === 'MKT';
  if (isMkt && rem > 0 && sessionKind !== 'rth') {
    const quoteName = order.side === 'SELL' ? 'bid' : 'ask';
    return {
      label: `${statusLabel} (MKT waits for open)`,
      title:
        `IBKR does not fill market orders outside regular hours. ` +
        `Fill now needs a live ${quoteName} on ${order.symbol.toUpperCase()} ` +
        `to sweep a limit -- or wait for 9:30 ET.`,
    };
  }
  return { label: statusLabel, title: order.status };
}

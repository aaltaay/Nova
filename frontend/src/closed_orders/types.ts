/** Closed Orders feature types (WID-027). Wire shape matches IbkrOrder. */
import type { IbkrOrder } from '../ibkr/types';

export type ClosedOrder = IbkrOrder;

export type ClosedOrdersFilter = 'all' | 'filled' | 'cancelled' | 'partial';

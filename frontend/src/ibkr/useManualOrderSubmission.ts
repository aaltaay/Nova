import { useState, type FormEvent } from 'react';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
} from '../execution_latency';
import {
  buildManualOrder,
  type ManualOrderPayload,
  type ManualOrderSide,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import { executionTransportError } from './executionTransportError';
import { notifyOrderRejected } from './notifyOrderRejected';
import { placeIbkrOrder, type PlaceOrderResult } from './placeOrder';
import { readSkipPlaceConfirm } from './placeConfirmPrefs';
import type {
  IbkrAccountSummary,
  IbkrMode,
  IbkrPosition,
} from './types';

interface Params {
  symbol: string;
  mode: IbkrMode;
  connected: boolean;
  spendLocked: boolean;
  needsPinUnlock: boolean;
  side: ManualOrderSide;
  shortEntry: boolean;
  shortBlockReason: string | null;
  orderType: ManualOrderType;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
  referencePrice: number | null;
  summary: IbkrAccountSummary | null;
  position: IbkrPosition | null;
  onNeedsPin: () => void;
  onOrderPlaced?: (result: PlaceOrderResult) => void;
}

export function useManualOrderSubmission(params: Params) {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirmSummary, setConfirmSummary] = useState<string | null>(null);

  function build() {
    return buildManualOrder(
      {
        symbol: params.symbol,
        side: params.side,
        orderType: params.orderType,
        quantityMode: params.quantityMode,
        quantityValue: params.quantityValue,
        limitPrice: params.limitPrice,
        stopPrice: params.stopPrice,
        outsideRth: params.outsideRth,
        shortEntry: params.shortEntry,
      },
      {
        marketReferencePrice: params.referencePrice,
        buyingPower: params.summary?.BuyingPower ?? null,
        positionQty: params.position?.qty ?? null,
      },
    );
  }

  function fail(
    text: string,
    reasonCode?: string | null,
    order?: ManualOrderPayload,
  ) {
    setResult({ ok: false, text });
    void notifyOrderRejected({
      message: text,
      reasonCode,
      order: order
        ? {
            symbol: order.symbol,
            side: order.side,
            qty: order.qty,
            mode: params.mode,
          }
        : undefined,
    });
  }

  async function executeOrder() {
    if (!params.connected || submitting) return;
    if (params.spendLocked) {
      fail('Orders remain locked by Nova environment safety settings.', 'ORDERS_GATE');
      return;
    }
    const timing = beginBrowserExecutionTiming(
      'manual_place',
      captureBrowserAction('user_action'),
    );
    const built = build();
    if (!built.ok) {
      fail(built.error);
      return;
    }

    setSubmitting(true);
    setResult(null);
    try {
      const response = await placeIbkrOrder(
        built.payload,
        undefined,
        { timing, referencePrice: params.referencePrice },
      );
      if (response.ok) {
        setResult({
          ok: true,
          text: `Order #${response.order_id} placed (${response.mode ?? params.mode})`,
        });
        params.onOrderPlaced?.(response);
      } else {
        fail(
          response.error ?? 'Order failed',
          response.reason_code,
          built.payload,
        );
      }
    } catch (error) {
      fail(executionTransportError(error));
    } finally {
      setSubmitting(false);
    }
  }

  function requestPlaceOrder() {
    if (!params.connected || submitting) return;
    if (params.spendLocked) {
      fail('Orders remain locked by Nova environment safety settings.', 'ORDERS_GATE');
      return;
    }
    if (params.shortEntry && params.shortBlockReason) {
      fail(params.shortBlockReason);
      return;
    }

    const built = build();
    if (!built.ok) {
      fail(built.error);
      return;
    }
    const priceText =
      params.orderType === 'LMT'
        ? ` @ $${params.limitPrice}`
        : params.orderType === 'STP'
          ? ` stop $${params.stopPrice}`
          : '';
    const hoursText = params.outsideRth
      ? ' including extended hours'
      : ' during regular hours';
    const direction = params.shortEntry ? 'SHORT' : params.side;
    const summaryText =
      `${direction} ${built.quantity} ${params.symbol.toUpperCase()} ` +
      `(${params.orderType}${priceText})${hoursText} on the ` +
      `${params.mode.toUpperCase()} account.`;

    if (readSkipPlaceConfirm()) {
      void executeOrder();
      return;
    }
    setConfirmSummary(summaryText);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!params.connected || submitting) return;
    if (params.needsPinUnlock) {
      params.onNeedsPin();
      return;
    }
    requestPlaceOrder();
  }

  function resetSubmission() {
    setResult(null);
    setConfirmSummary(null);
  }

  return {
    submitting,
    result,
    confirmSummary,
    submit,
    executeOrder,
    setConfirmSummary,
    resetSubmission,
  };
}

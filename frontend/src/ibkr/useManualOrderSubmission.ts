import { useRef, useState, type FormEvent } from 'react';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
} from '../execution_latency';
import {
  buildManualOrder,
  manualOrderConfirmPriceText,
  type BuildOrderResult,
  type ManualOrderPayload,
  type ManualOrderSide,
  type ManualOrderType,
  type QuantityMode,
} from './orderEntry';
import { planProtectiveLegs } from './protectiveLegs';
import { readTradeDefaultsPrefs } from '../settings/tradeDefaultsPrefs';
import { executionTransportError } from './executionTransportError';
import { newGestureKey } from './gestureKey';
import { notifyOrderRejected } from './notifyOrderRejected';
import { beginDeskAction } from './deskActionFlight';
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
  // `submitting` state lands a render later — a double-click inside one tick
  // would pass it and place twice. The refs close that window and keep one
  // idempotency key for the whole click → confirm → place gesture (D-011).
  const inFlightRef = useRef(false);
  const gestureKeyRef = useRef<string | null>(null);

  // #91: Settings owns TIF and the optional default TP/SL. Read per render
  // (localStorage, like the ticket's other defaults) so a Settings change
  // reaches the next order instead of waiting for a remount.
  const prefs = readTradeDefaultsPrefs();
  const limitNumber = Number(params.limitPrice);
  const legsPlan = planProtectiveLegs({
    prefs,
    side: params.side,
    shortEntry: params.shortEntry,
    orderType: params.orderType,
    limitPrice:
      Number.isFinite(limitNumber) && limitNumber > 0 ? limitNumber : null,
    positionQty: params.position?.qty ?? null,
    mode: params.mode,
  });
  const legsNote = legsPlan.kind === 'refuse' ? legsPlan.error : legsPlan.note;

  function build(): BuildOrderResult {
    const built = buildManualOrder(
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
    if (!built.ok) return built;
    // Defaults on but this entry cannot carry legs: refuse instead of placing
    // the unprotected order the operator asked Nova to stop sending.
    if (legsPlan.kind === 'refuse') return { ok: false, error: legsPlan.error };
    return {
      ...built,
      payload: {
        ...built.payload,
        tif: prefs.tif,
        ...(legsPlan.kind === 'attach'
          ? {
              take_profit_price: legsPlan.takeProfitPrice,
              stop_loss_price: legsPlan.stopLossPrice,
            }
          : {}),
      },
    };
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
    if (!params.connected || submitting || inFlightRef.current) return;
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

    inFlightRef.current = true;
    const endDeskAction = beginDeskAction();
    const idempotencyKey = gestureKeyRef.current ?? newGestureKey('manual');
    gestureKeyRef.current = idempotencyKey;
    setSubmitting(true);
    setResult(null);
    try {
      const response = await placeIbkrOrder(
        built.payload,
        idempotencyKey,
        { timing, referencePrice: params.referencePrice },
      );
      if (response.ok) {
        const legs =
          response.target_order_id && response.stop_order_id
            ? ` + TP #${response.target_order_id} / SL #${response.stop_order_id}`
            : '';
        setResult({
          ok: true,
          text:
            `Order #${response.order_id} placed${legs} ` +
            `(${response.mode ?? params.mode})`,
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
      endDeskAction();
      inFlightRef.current = false;
      gestureKeyRef.current = null;
      setSubmitting(false);
    }
  }

  function requestPlaceOrder() {
    if (!params.connected || submitting || inFlightRef.current) return;
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
    const priceText = manualOrderConfirmPriceText({
      orderType: params.orderType,
      limitPrice: params.limitPrice,
      stopPrice: params.stopPrice,
    });
    const hoursText = params.outsideRth
      ? ' including extended hours'
      : ' during regular hours';
    const direction = params.shortEntry ? 'SHORT' : params.side;
    // DAY and no legs read exactly as before; GTC / a bracket must be said out
    // loud, because both outlive the click that placed them.
    const tifText = prefs.tif === 'DAY' ? '' : `, ${prefs.tif}`;
    const legsText = legsPlan.kind === 'attach' ? ` ${legsPlan.note}.` : '';
    const summaryText =
      `${direction} ${built.quantity} ${params.symbol.toUpperCase()} ` +
      `(${params.orderType}${priceText}${tifText})${hoursText} on the ` +
      `${params.mode.toUpperCase()} account.${legsText}`;

    // One key for this click, whether it places straight away or waits on the
    // confirm dialog — a double-clicked Confirm replays instead of re-placing.
    gestureKeyRef.current = newGestureKey('manual');
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
    gestureKeyRef.current = null;
    setResult(null);
    setConfirmSummary(null);
  }

  return {
    submitting,
    result,
    confirmSummary,
    legsNote,
    legsBlocked: legsPlan.kind === 'refuse',
    submit,
    executeOrder,
    setConfirmSummary,
    resetSubmission,
    /** Put another action's outcome on the ticket's Last line (the rail's Flatten, QA R32). */
    showResult: setResult,
  };
}

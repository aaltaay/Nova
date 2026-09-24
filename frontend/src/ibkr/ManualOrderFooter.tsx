import { Button } from '@/components/ui/button';
import {
  TICKER_TRADE_DISARMED_LABEL,
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_ORDERS_LOCKED_LABEL,
  TICKER_TRADE_UNLOCK_LABEL,
} from '../constants';
import {
  TICKET_LAST_LABEL,
  TICKET_WHY_SENDING,
} from '../constantGroups/trader_chrome';
import { EstChip } from '../stock_view/EstChip';
import {
  GATEWAY_STATUS_KNOWN,
  gatewayLockWhy,
  gatewayPlaceLabel,
  type GatewayStatusFact,
} from './gatewayStatusWording';
import { PlaceOrderConfirmDialog } from './PlaceOrderConfirmDialog';
import { writeSkipPlaceConfirm } from './placeConfirmPrefs';
import { placeActionLabel, type TicketSide } from './ticketSide';

interface Props {
  isPaper: boolean;
  /** Paper or Sim: a placed order's fill will be an estimate, so `Last:` carries the est chip. */
  practice?: boolean;
  ticketSide?: TicketSide;
  symbol?: string;
  needsPinUnlock: boolean;
  connected: boolean;
  /** Whether `connected: false` is a status answer or an unknown (QA D10, #459). */
  gatewayStatus?: GatewayStatusFact;
  submitting: boolean;
  spendLocked: boolean;
  spendLockReason?: string | null;
  /** ADR 018: the env permits spending but this process is not armed -- a venue change or restart. */
  spendDisarmed?: boolean;
  quantityLocked: boolean;
  forcedQty: number | null;
  /** MASTER TEST QTY GATE (#444): "Live cap: sends N of M shares", or null (Paper / Sim). */
  qtyCapNote?: string | null;
  sessionUnlocked: boolean;
  result: { ok: boolean; text: string } | null;
  confirmSummary: string | null;
  onConfirmClose: () => void;
  onConfirmPlace: () => void;
}

export function ManualOrderFooter({
  isPaper,
  practice = false,
  ticketSide = 'buy',
  symbol = '',
  needsPinUnlock,
  connected,
  gatewayStatus = GATEWAY_STATUS_KNOWN,
  submitting,
  spendLocked,
  spendLockReason = null,
  spendDisarmed = false,
  quantityLocked,
  forcedQty,
  qtyCapNote = null,
  sessionUnlocked,
  result,
  confirmSummary,
  onConfirmClose,
  onConfirmPlace,
}: Props) {
  const placeLabel = placeActionLabel(ticketSide, symbol);
  const lockReason =
    spendLockReason ?? 'IBKR orders remain gated by environment safety settings';
  // Unlock is not a place — keep the unlock affordance reachable while locked so
  // the operator is never stuck, but never offer Place into a certain reject.
  const placeBlockedBySpend = spendLocked && !needsPinUnlock;
  // A locked Place says why (ux/whyTip.ts); the native title only describes a Place that works.
  const placeWhy = !connected
    ? gatewayLockWhy(gatewayStatus)
    : submitting
      ? TICKET_WHY_SENDING
      : placeBlockedBySpend
        ? lockReason
        : null;
  const buttonText = !connected
    ? gatewayPlaceLabel(gatewayStatus)
    : needsPinUnlock
      ? TICKER_TRADE_UNLOCK_LABEL
      : placeBlockedBySpend
        ? spendDisarmed
          ? TICKER_TRADE_DISARMED_LABEL
          : TICKER_TRADE_ORDERS_LOCKED_LABEL
        : submitting
          ? 'Placing…'
          : placeLabel;
  const buttonTitle = needsPinUnlock
    ? `Unlock trading, then ${placeLabel}`
    : quantityLocked
      ? `Quantity locked to ${TICKER_TRADE_FORCE_QTY} share (temporary safety)`
      : isPaper
        ? "Review and place this order on Nova's practice account (fake money)"
        : 'Review and place this order';

  return (
    <>
      <Button
        type="submit"
        variant="default"
        size="lg"
        className={
          ticketSide === 'short' && !needsPinUnlock && connected
            ? 'manual-order-submit manual-order-submit--short mt-1 w-full'
            : isPaper && !needsPinUnlock && connected
            ? 'manual-order-submit manual-order-submit--paper mt-1 w-full'
            : 'manual-order-submit mt-1 w-full'
        }
        data-testid="manual-order-submit"
        disabled={placeWhy != null}
        title={placeWhy != null ? undefined : buttonTitle}
        data-why={placeWhy || undefined}
      >
        {buttonText}
      </Button>

      {needsPinUnlock && connected && (
        <span className="manual-order-lock-note">
          Unlock trading to enable {placeLabel}.
        </span>
      )}
      {spendLocked && (
        <span
          className="manual-order-lock-note manual-order-lock-note--spend"
          data-testid="spend-lock-note"
        >
          {lockReason}
        </span>
      )}
      {quantityLocked && sessionUnlocked && (
        <span className="manual-order-lock-note">
          Quantity locked to {forcedQty} share for safety — presets ignored.
        </span>
      )}
      {qtyCapNote && (
        <span className="manual-order-lock-note" data-testid="qty-cap-note">
          {qtyCapNote}
        </span>
      )}
      {result && (
        <span
          className={`manual-order-result ${result.ok ? 'ok' : 'err'}`}
          data-testid="manual-order-result"
        >
          <span className="mot-last__k">{TICKET_LAST_LABEL}</span>
          {result.text}
          {practice && result.ok ? (
            <>
              {' '}
              <EstChip />
            </>
          ) : null}
        </span>
      )}

      <PlaceOrderConfirmDialog
        open={confirmSummary != null}
        summary={confirmSummary ?? ''}
        onCancel={onConfirmClose}
        onConfirm={skipNextTime => {
          if (skipNextTime) writeSkipPlaceConfirm(true);
          onConfirmClose();
          onConfirmPlace();
        }}
      />
    </>
  );
}

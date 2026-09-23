import { Button } from '@/components/ui/button';
import {
  TICKER_TRADE_DISARMED_LABEL,
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_ORDERS_LOCKED_LABEL,
  TICKER_TRADE_UNLOCK_LABEL,
} from '../constants';
import { TICKET_LAST_LABEL } from '../constantGroups/trader_chrome';
import { EstChip } from '../stock_view/EstChip';
import { PlaceOrderConfirmDialog } from './PlaceOrderConfirmDialog';
import { writeSkipPlaceConfirm } from './placeConfirmPrefs';
import { placeActionLabel, type TicketSide } from './ticketSide';
import { TradingPinDialog } from './TradingPinDialog';

interface Props {
  isPaper: boolean;
  /** Paper or Sim: a placed order's fill will be an estimate, so `Last:` carries the est chip. */
  practice?: boolean;
  ticketSide?: TicketSide;
  symbol?: string;
  needsPinUnlock: boolean;
  connected: boolean;
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
  pinDialogOpen: boolean;
  onConfirmClose: () => void;
  onConfirmPlace: () => void;
  onPinSubmit: (pin: string) => boolean;
  onPinClose: () => void;
}

export function ManualOrderFooter({
  isPaper,
  practice = false,
  ticketSide = 'buy',
  symbol = '',
  needsPinUnlock,
  connected,
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
  pinDialogOpen,
  onConfirmClose,
  onConfirmPlace,
  onPinSubmit,
  onPinClose,
}: Props) {
  const placeLabel = placeActionLabel(ticketSide, symbol);
  const lockReason =
    spendLockReason ?? 'IBKR orders remain gated by environment safety settings';
  // Unlock is not a place — keep the PIN affordance reachable while locked so
  // the operator is never stuck, but never offer Place into a certain reject.
  const placeBlockedBySpend = spendLocked && !needsPinUnlock;
  const buttonText = !connected
    ? 'Connect IB Gateway'
    : needsPinUnlock
      ? TICKER_TRADE_UNLOCK_LABEL
      : placeBlockedBySpend
        ? spendDisarmed
          ? TICKER_TRADE_DISARMED_LABEL
          : TICKER_TRADE_ORDERS_LOCKED_LABEL
        : submitting
          ? 'Placing…'
          : placeLabel;
  const buttonTitle = !connected
    ? 'Connect IB Gateway first'
    : needsPinUnlock
      ? `Enter unlock code, then ${placeLabel}`
      : spendLocked
        ? lockReason
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
        disabled={!connected || submitting || placeBlockedBySpend}
        title={buttonTitle}
      >
        {buttonText}
      </Button>

      {needsPinUnlock && connected && (
        <span className="manual-order-lock-note">
          Enter the unlock code to enable {placeLabel}.
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

      <TradingPinDialog
        open={pinDialogOpen}
        onSubmit={onPinSubmit}
        onCancel={onPinClose}
      />
    </>
  );
}

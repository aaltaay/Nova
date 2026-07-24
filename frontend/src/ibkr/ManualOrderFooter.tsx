import { Button } from '@/components/ui/button';
import {
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_PLACE_ORDER_LABEL,
  TICKER_TRADE_PLACE_PAPER_ORDER_LABEL,
  TICKER_TRADE_UNLOCK_LABEL,
} from '../constants';
import { PlaceOrderConfirmDialog } from './PlaceOrderConfirmDialog';
import { writeSkipPlaceConfirm } from './placeConfirmPrefs';
import { TradingPinDialog } from './TradingPinDialog';

interface Props {
  isPaper: boolean;
  needsPinUnlock: boolean;
  connected: boolean;
  submitting: boolean;
  spendLocked: boolean;
  quantityLocked: boolean;
  forcedQty: number | null;
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
  needsPinUnlock,
  connected,
  submitting,
  spendLocked,
  quantityLocked,
  forcedQty,
  sessionUnlocked,
  result,
  confirmSummary,
  pinDialogOpen,
  onConfirmClose,
  onConfirmPlace,
  onPinSubmit,
  onPinClose,
}: Props) {
  const placeLabel = isPaper
    ? TICKER_TRADE_PLACE_PAPER_ORDER_LABEL
    : TICKER_TRADE_PLACE_ORDER_LABEL;
  const buttonText = !connected
    ? 'Connect IB Gateway'
    : needsPinUnlock
      ? TICKER_TRADE_UNLOCK_LABEL
      : submitting
        ? 'Placing…'
        : placeLabel;
  const buttonTitle = !connected
    ? 'Connect IB Gateway first'
    : needsPinUnlock
      ? `Enter unlock code, then ${placeLabel}`
      : spendLocked
        ? 'IBKR orders remain gated by environment safety settings'
        : quantityLocked
          ? `Quantity locked to ${TICKER_TRADE_FORCE_QTY} share (temporary safety)`
          : isPaper
            ? 'Review and place this order on the IBKR paper account'
            : 'Review and place this order';

  return (
    <>
      <Button
        type="submit"
        variant="default"
        size="lg"
        className={
          isPaper && !needsPinUnlock && connected
            ? 'manual-order-submit manual-order-submit--paper mt-1 w-full'
            : 'manual-order-submit mt-1 w-full'
        }
        disabled={!connected || submitting}
        title={buttonTitle}
      >
        {buttonText}
      </Button>

      {needsPinUnlock && connected && (
        <span className="manual-order-lock-note">
          Enter the unlock code to enable {placeLabel}.
        </span>
      )}
      {sessionUnlocked && spendLocked && (
        <span className="manual-order-lock-note">
          Session unlocked. IBKR env gates may still reject the order until orders are enabled.
        </span>
      )}
      {quantityLocked && sessionUnlocked && (
        <span className="manual-order-lock-note">
          Quantity locked to {forcedQty} share for safety — presets ignored.
        </span>
      )}
      {result && (
        <span className={`manual-order-result ${result.ok ? 'ok' : 'err'}`}>
          {result.text}
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

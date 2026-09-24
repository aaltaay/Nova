/**
 * Live PIN prompt -- shadcn Dialog + InputOTP.
 *
 * The dialog only collects digits: the backend checks the PIN against the hash
 * in `.env` (`POST /api/ibkr/arm`), and whatever it answers is shown as-is.
 */
import { useEffect, useState } from 'react';
import { Lock } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from '@/components/ui/input-otp';
import {
  TICKER_TRADE_UNLOCK_DIALOG_CANCEL,
  TICKER_TRADE_UNLOCK_DIALOG_CHECKING,
  TICKER_TRADE_UNLOCK_DIALOG_CHECKING_WHY,
  TICKER_TRADE_UNLOCK_DIALOG_SUBTITLE,
  TICKER_TRADE_UNLOCK_DIALOG_TITLE,
  TICKER_TRADE_UNLOCK_PIN_LENGTH,
} from '../constants';

interface Props {
  open: boolean;
  /** Resolves null when the backend accepted the PIN, else the reason to show. */
  onSubmit: (pin: string) => Promise<string | null>;
  onCancel: () => void;
  /** Shown before any PIN is typed (e.g. the Live PIN is not set). */
  notice?: string | null;
}

export function TradingPinDialog({ open, onSubmit, onCancel, notice = null }: Props) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  useEffect(() => {
    if (open) {
      setValue('');
      setError(null);
      setPending(false);
      setResetKey(k => k + 1);
    }
  }, [open]);

  async function trySubmit(pin: string) {
    if (pin.length !== TICKER_TRADE_UNLOCK_PIN_LENGTH || pending) return;
    setPending(true);
    let refusal: string | null;
    try {
      refusal = await onSubmit(pin);
    } catch (err) {
      console.warn('[Nova] PIN submit failed', err);
      refusal = err instanceof Error && err.message ? err.message : String(err);
    }
    setPending(false);
    if (refusal == null) return;
    setError(refusal);
    setValue('');
    setResetKey(k => k + 1);
  }

  const message = error ?? notice;

  return (
    <Dialog open={open} onOpenChange={next => !next && onCancel()}>
      <DialogContent
        showCloseButton={false}
        className="border-border bg-card text-card-foreground sm:max-w-sm"
      >
        <DialogHeader className="items-center text-center sm:text-center">
          <div className="mb-2 flex size-14 items-center justify-center rounded-full bg-primary/15 text-primary">
            <Lock className="size-6" />
          </div>
          <DialogTitle className="text-xl">{TICKER_TRADE_UNLOCK_DIALOG_TITLE}</DialogTitle>
          <p className="text-sm text-muted-foreground">{TICKER_TRADE_UNLOCK_DIALOG_SUBTITLE}</p>
        </DialogHeader>

        <div className="flex justify-center">
          <InputOTP
            key={resetKey}
            maxLength={TICKER_TRADE_UNLOCK_PIN_LENGTH}
            value={value}
            disabled={pending}
            data-why={pending ? TICKER_TRADE_UNLOCK_DIALOG_CHECKING_WHY : undefined}
            onChange={next => {
              setValue(next);
              setError(null);
              if (next.length === TICKER_TRADE_UNLOCK_PIN_LENGTH) {
                void trySubmit(next);
              }
            }}
            autoFocus
          >
            <InputOTPGroup className={error ? '[&_[data-slot=input-otp-slot]]:border-destructive' : undefined}>
              {Array.from({ length: TICKER_TRADE_UNLOCK_PIN_LENGTH }, (_, index) => (
                <InputOTPSlot key={index} index={index} />
              ))}
            </InputOTPGroup>
          </InputOTP>
        </div>

        {pending ? (
          <p className="text-center text-sm text-muted-foreground" role="status">
            {TICKER_TRADE_UNLOCK_DIALOG_CHECKING}
          </p>
        ) : message ? (
          <p className="text-center text-sm text-destructive" role="alert" data-testid="trading-pin-error">
            {message}
          </p>
        ) : null}

        <Button type="button" variant="outline" className="w-full" onClick={onCancel}>
          {TICKER_TRADE_UNLOCK_DIALOG_CANCEL}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

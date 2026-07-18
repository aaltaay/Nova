/** Trade-ticket PIN unlock — shadcn Dialog + InputOTP. */
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
  TICKER_TRADE_UNLOCK_DIALOG_SUBTITLE,
  TICKER_TRADE_UNLOCK_DIALOG_TITLE,
  TICKER_TRADE_UNLOCK_FAIL,
  TICKER_TRADE_UNLOCK_PIN_LENGTH,
} from '../constants';

interface Props {
  open: boolean;
  onSubmit: (pin: string) => boolean;
  onCancel: () => void;
}

export function TradingPinDialog({ open, onSubmit, onCancel }: Props) {
  const [value, setValue] = useState('');
  const [failed, setFailed] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  useEffect(() => {
    if (open) {
      setValue('');
      setFailed(false);
      setResetKey(k => k + 1);
    }
  }, [open]);

  function trySubmit(pin: string) {
    if (pin.length !== TICKER_TRADE_UNLOCK_PIN_LENGTH) return;
    if (onSubmit(pin)) return;
    setFailed(true);
    setValue('');
    setResetKey(k => k + 1);
  }

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
            onChange={next => {
              setValue(next);
              setFailed(false);
              if (next.length === TICKER_TRADE_UNLOCK_PIN_LENGTH) {
                trySubmit(next);
              }
            }}
            autoFocus
          >
            <InputOTPGroup className={failed ? '[&_[data-slot=input-otp-slot]]:border-destructive' : undefined}>
              {Array.from({ length: TICKER_TRADE_UNLOCK_PIN_LENGTH }, (_, index) => (
                <InputOTPSlot key={index} index={index} />
              ))}
            </InputOTPGroup>
          </InputOTP>
        </div>

        {failed && (
          <p className="text-center text-sm text-destructive">{TICKER_TRADE_UNLOCK_FAIL}</p>
        )}

        <Button type="button" variant="outline" className="w-full" onClick={onCancel}>
          {TICKER_TRADE_UNLOCK_DIALOG_CANCEL}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

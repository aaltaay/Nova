/** Place-order confirmation — shadcn AlertDialog + skip-next-time checkbox. */
import { useEffect, useId, useState } from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  TICKER_TRADE_ORDER_DISCLOSURE,
  TICKER_TRADE_PLACE_CONFIRM_CANCEL,
  TICKER_TRADE_PLACE_CONFIRM_SKIP_LABEL,
  TICKER_TRADE_PLACE_CONFIRM_SUBMIT,
  TICKER_TRADE_PLACE_CONFIRM_TITLE,
} from '../constants';

interface Props {
  summary: string;
  open: boolean;
  onConfirm: (skipNextTime: boolean) => void;
  onCancel: () => void;
}

export function PlaceOrderConfirmDialog({
  summary,
  open,
  onConfirm,
  onCancel,
}: Props) {
  const skipId = useId();
  const [skipNextTime, setSkipNextTime] = useState(false);

  useEffect(() => {
    if (open) setSkipNextTime(false);
  }, [open]);

  return (
    <AlertDialog
      open={open}
      onOpenChange={next => {
        if (!next) onCancel();
      }}
    >
      <AlertDialogContent className="border-border bg-card text-card-foreground">
        <AlertDialogHeader>
          <AlertDialogTitle>{TICKER_TRADE_PLACE_CONFIRM_TITLE}</AlertDialogTitle>
          <AlertDialogDescription className="space-y-2 text-left">
            <span className="block">{TICKER_TRADE_ORDER_DISCLOSURE}</span>
            <span className="block font-semibold text-foreground">{summary}</span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <label
          className="flex cursor-pointer items-start gap-2 text-sm text-muted-foreground"
          htmlFor={skipId}
        >
          <input
            id={skipId}
            type="checkbox"
            className="mt-1"
            checked={skipNextTime}
            onChange={event => setSkipNextTime(event.target.checked)}
          />
          <span>{TICKER_TRADE_PLACE_CONFIRM_SKIP_LABEL}</span>
        </label>
        <AlertDialogFooter>
          <AlertDialogCancel type="button" onClick={onCancel}>
            {TICKER_TRADE_PLACE_CONFIRM_CANCEL}
          </AlertDialogCancel>
          <AlertDialogAction
            type="button"
            onClick={() => onConfirm(skipNextTime)}
          >
            {TICKER_TRADE_PLACE_CONFIRM_SUBMIT}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/**
 * Loud pop-up for place/flatten rejects. The ticket footer span is too easy
 * to miss (BUYING_POWER was a one-line err under Place).
 */
import {
  ORDER_REJECT_DEFAULT_TITLE,
  ORDER_REJECT_SKIP_MESSAGES,
  ORDER_REJECT_TITLES,
} from '../constants';
import { alertApp } from '../ux';

export function inferOrderRejectReason(
  message: string,
  reasonCode?: string | null,
): string | null {
  if (reasonCode) return reasonCode;
  if (/exceeds BuyingPower/i.test(message)) return 'BUYING_POWER';
  if (/BuyingPower (not yet available|unavailable)/i.test(message)) {
    return 'BUYING_POWER_UNKNOWN';
  }
  return null;
}

export function orderRejectTitle(reasonCode?: string | null): string {
  if (!reasonCode) return ORDER_REJECT_DEFAULT_TITLE;
  return ORDER_REJECT_TITLES[reasonCode] ?? ORDER_REJECT_DEFAULT_TITLE;
}

export function orderRejectTone(
  reasonCode?: string | null,
): 'warning' | 'danger' {
  return reasonCode === 'BUYING_POWER' || reasonCode === 'BUYING_POWER_UNKNOWN'
    ? 'warning'
    : 'danger';
}

export function notifyOrderRejected(opts: {
  message: string;
  reasonCode?: string | null;
  title?: string;
}): void {
  const message = (opts.message || '').trim();
  if (!message || ORDER_REJECT_SKIP_MESSAGES.includes(message)) return;
  const reason = inferOrderRejectReason(message, opts.reasonCode);
  try {
    void alertApp({
      title: opts.title ?? orderRejectTitle(reason),
      message,
      tone: orderRejectTone(reason),
    });
  } catch {
    // AppDialogHost missing (tests / a tree without the host). Inline result stays.
  }
}

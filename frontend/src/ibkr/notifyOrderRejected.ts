/**
 * Loud pop-up for place/flatten rejects. The ticket footer span is too easy
 * to miss (BUYING_POWER was a one-line err under Place).
 */
import {
  IBKR_CLIENT_PORTAL_URL,
  IBKR_VERIFICATION_CONFIRMED_LABEL,
  IBKR_VERIFICATION_OPEN_PORTAL_LABEL,
  IBKR_VERIFICATION_REQUIRED_REASON,
  ORDER_REJECT_DEFAULT_TITLE,
  ORDER_REJECT_SKIP_MESSAGES,
  ORDER_REJECT_TITLES,
} from '../constants';
import { alertApp, confirmApp } from '../ux';
import { acknowledgeIbkrVerification } from './acknowledgeVerification';
import { isSoftOrderWarning } from './orderFillHonesty';
import { openIbkrClientPortal } from './openIbkrClientPortal';

export function inferOrderRejectReason(
  message: string,
  reasonCode?: string | null,
): string | null {
  if (reasonCode) return reasonCode;
  if (/exceeds BuyingPower/i.test(message)) return 'BUYING_POWER';
  if (/BuyingPower (not yet available|unavailable)/i.test(message)) {
    return 'BUYING_POWER_UNKNOWN';
  }
  if (/login to client portal[\s\S]*verify using the token/i.test(message)) {
    return IBKR_VERIFICATION_REQUIRED_REASON;
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

export interface RejectedOrderContext {
  symbol: string;
  side: string;
  qty: number;
  mode?: string | null;
}

export async function notifyOrderRejected(opts: {
  message: string;
  reasonCode?: string | null;
  title?: string;
  order?: RejectedOrderContext;
}): Promise<boolean> {
  const message = (opts.message || '').trim();
  if (!message || ORDER_REJECT_SKIP_MESSAGES.includes(message)) return false;
  if (isSoftOrderWarning(message, opts.reasonCode)) return false;
  const reason = inferOrderRejectReason(message, opts.reasonCode);
  try {
    if (reason === IBKR_VERIFICATION_REQUIRED_REASON) {
      const order = opts.order;
      const summary = order
        ? `${(order.mode || 'IBKR').toUpperCase()} ${order.side.toUpperCase()} ${order.qty} ${order.symbol.toUpperCase()}`
        : null;
      const confirmed = await confirmApp({
        title: opts.title ?? orderRejectTitle(reason),
        message: [
          message,
          summary ? `Order: ${summary}` : null,
          'Open the official IBKR Client Portal, complete token verification, and wait a few minutes. Nova will not retry automatically.',
        ].filter(Boolean).join('\n\n'),
        tone: 'danger',
        confirmLabel: IBKR_VERIFICATION_CONFIRMED_LABEL,
        cancelLabel: 'Close',
        auxiliaryLabel: IBKR_VERIFICATION_OPEN_PORTAL_LABEL,
        onAuxiliary: () => {
          void openIbkrClientPortal().catch(() => {
            void alertApp({
              title: 'Could not open Client Portal',
              message: IBKR_CLIENT_PORTAL_URL,
              tone: 'warning',
            });
          });
        },
      });
      if (!confirmed || !order?.symbol) return false;
      try {
        const acknowledged = await acknowledgeIbkrVerification(order.symbol);
        if (acknowledged) return true;
      } catch {
        // The actionable alert below owns the failure surface.
      }
      void alertApp({
        title: 'Verification acknowledgment failed',
        message:
          'Nova could not clear the entry block. Your order remains blocked; reconnect the API and acknowledge verification again.',
        tone: 'danger',
      }).catch(() => undefined);
      return false;
    }
    await alertApp({
      title: opts.title ?? orderRejectTitle(reason),
      message,
      tone: orderRejectTone(reason),
    });
    return false;
  } catch {
    // AppDialogHost missing (tests / a tree without the host). Inline result stays.
    return false;
  }
}

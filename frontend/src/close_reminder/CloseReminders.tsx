/**
 * The close-of-day reminder cards: mounted once with the app bar (the main desk window), fed the
 * desk's positions and venue as props so the feature imports no other feature's internals. A card
 * is loud on purpose (role="alert"): a reminder the operator misses is no reminder. "Open X" shows the Trader tab; the card stays until the position is flat, the operator
 * dismisses it, or 16:00. Nothing here places, stages or cancels an order.
 */
import { useEffect, useSyncExternalStore } from 'react';
import {
  CLOSE_REMIND_DISMISS,
  CLOSE_REMIND_REGION,
  CLOSE_REMIND_TICK_MS,
  closeReminderBody,
  closeReminderOpen,
  closeReminderTitle,
} from './closeReminderConstants';
import {
  dismissCloseReminder,
  getCloseReminders,
  noteCloseReminders,
  subscribeCloseReminders,
  type CloseReminder,
  type HeldPosition,
} from './closeReminderStore';
import './closeReminder.css';

export interface CloseRemindersProps {
  positions: readonly HeldPosition[];
  /** The desk venue; cards only on live and paper. */
  venue: string | null | undefined;
  /** The rows are last-known (the Gateway dropped). */
  stale?: boolean;
  /** Nova covers Live shorts at 15:55: IBKR_SHORT_ENABLED is on (ADR 048 step 6). */
  liveCover?: boolean;
  onOpenSymbol?: (symbol: string) => void;
}

function CloseReminderCard({ reminder, liveCover, onOpenSymbol }: {
  reminder: CloseReminder;
  liveCover: boolean;
  onOpenSymbol?: (symbol: string) => void;
}) {
  const { symbol } = reminder;
  return (
    <div
      className={`close-reminder is-${reminder.stage}`}
      role="alert"
      data-testid="close-reminder"
      data-symbol={symbol}
      data-stage={reminder.stage}
    >
      <div className="close-reminder__text">
        <strong className="close-reminder__title" data-testid="close-reminder-title">
          {closeReminderTitle(reminder, liveCover)}
        </strong>
        <span className="close-reminder__body">{closeReminderBody(reminder, liveCover)}</span>
        {onOpenSymbol ? (
          <div className="close-reminder__actions">
            <button
              type="button"
              className="close-reminder__action"
              data-testid="close-reminder-open"
              onClick={() => onOpenSymbol(symbol)}
            >
              {closeReminderOpen(symbol)}
            </button>
          </div>
        ) : null}
      </div>
      <button
        type="button"
        className="close-reminder__dismiss"
        data-testid="close-reminder-dismiss"
        aria-label={CLOSE_REMIND_DISMISS}
        title={CLOSE_REMIND_DISMISS}
        onClick={() => dismissCloseReminder(symbol)}
      >
        ×
      </button>
    </div>
  );
}

export function CloseReminders({ positions, venue, stale = false, liveCover = false, onOpenSymbol }: CloseRemindersProps) {
  const reminders = useSyncExternalStore(subscribeCloseReminders, getCloseReminders, getCloseReminders);
  useEffect(() => {
    const tick = () => noteCloseReminders(positions, venue, stale);
    tick();
    const id = window.setInterval(tick, CLOSE_REMIND_TICK_MS);
    return () => window.clearInterval(id);
  }, [positions, venue, stale]);

  if (reminders.length === 0) return null;
  return (
    <div className="close-reminders" role="region" aria-label={CLOSE_REMIND_REGION} data-testid="close-reminders">
      {reminders.map(reminder => (
        <CloseReminderCard key={reminder.symbol} reminder={reminder} liveCover={liveCover} onOpenSymbol={onOpenSymbol} />
      ))}
    </div>
  );
}

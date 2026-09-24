/**
 * Settings > Trade > Practice Account: reset one venue's practice ledger.
 * Confirms through the app dialog; the optional starting cash rides on the POST.
 */
import { useState } from 'react';
import {
  PRACTICE_PAPER_ARCHIVE_NOTE,
  PRACTICE_RESET_CONFIRM_LABEL,
  PRACTICE_RESET_FAILED,
  PRACTICE_SIM_RESET_NOTE,
  PRACTICE_STARTING_CASH_LABEL,
  PRACTICE_STARTING_CASH_PLACEHOLDER,
  PRACTICE_VENUE_LABELS,
  practiceResetBusyWhy,
  practiceResetButtonLabel,
  practiceResetConfirmMessage,
  practiceResetConfirmTitle,
  practiceResetDone,
  type PracticeVenue,
} from '../constantGroups/practice';
import { formatMoney } from '../utils/formatMoney';
import { confirmApp } from '../ux';
import { resetPracticeAccount } from './practiceAccountResource';
import { parseStartingCash } from './practiceReset';

export function PracticeResetAction({ venue }: { venue: PracticeVenue }) {
  const [startingCash, setStartingCash] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const inputId = `practice-reset-cash-${venue}`;
  const busyWhy = busy ? practiceResetBusyWhy(venue) : undefined;

  const reset = async () => {
    const parsed = parseStartingCash(startingCash);
    if (!parsed.ok) {
      setNotice({ tone: 'error', text: parsed.error });
      return;
    }
    const confirmed = await confirmApp({
      title: practiceResetConfirmTitle(venue),
      message: practiceResetConfirmMessage(
        venue,
        parsed.value == null ? null : formatMoney(parsed.value, 0),
      ),
      confirmLabel: PRACTICE_RESET_CONFIRM_LABEL,
      tone: 'warning',
    });
    if (!confirmed) return;
    setBusy(true);
    setNotice(null);
    try {
      const account = await resetPracticeAccount(venue, parsed.value);
      setNotice({ tone: 'ok', text: practiceResetDone(venue, formatMoney(account.cash)) });
      setStartingCash('');
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      setNotice({ tone: 'error', text: `${PRACTICE_RESET_FAILED}: ${detail}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="practice-reset" data-testid={`practice-reset-${venue}`} data-venue={venue}>
      <div className="practice-reset__head">
        <strong>{PRACTICE_VENUE_LABELS[venue]}</strong>
        <span className="settings-block-hint">
          {venue === 'paper' ? PRACTICE_PAPER_ARCHIVE_NOTE : PRACTICE_SIM_RESET_NOTE}
        </span>
      </div>
      <div className="trade-defaults-row">
        <label htmlFor={inputId}>{PRACTICE_STARTING_CASH_LABEL}</label>
        <input
          id={inputId}
          type="text"
          inputMode="numeric"
          placeholder={PRACTICE_STARTING_CASH_PLACEHOLDER}
          value={startingCash}
          disabled={busy}
          data-why={busyWhy}
          onChange={(e) => {
            setStartingCash(e.target.value);
            setNotice(null);
          }}
          data-testid={`practice-reset-cash-${venue}`}
        />
      </div>
      <button
        type="button"
        className="btn-secondary practice-reset__button"
        disabled={busy}
        data-why={busyWhy}
        onClick={() => void reset()}
        data-testid={`practice-reset-button-${venue}`}
      >
        {practiceResetButtonLabel(venue)}
      </button>
      {notice && (
        <p
          className={`settings-block-hint practice-reset__notice practice-reset__notice--${notice.tone}`}
          role={notice.tone === 'error' ? 'alert' : 'status'}
          data-testid={`practice-reset-notice-${venue}`}
        >
          {notice.text}
        </p>
      )}
    </div>
  );
}

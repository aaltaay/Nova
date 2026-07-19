/** Stock View header capsules — operator mode, Paper/Live.
 * Reflects IBKR status only; never bypasses spend / live confirmation gates. */
import {
  STOCK_VIEW_ACCOUNT_MODE_LIVE,
  STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE,
  STOCK_VIEW_ACCOUNT_MODE_PAPER,
  STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE,
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO,
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO_TITLE,
  STOCK_VIEW_OPERATOR_MODE_MANUAL,
  STOCK_VIEW_OPERATOR_MODE_MANUAL_TITLE,
  STOCK_VIEW_OPERATOR_MODE_NORMAL,
  STOCK_VIEW_OPERATOR_MODE_NORMAL_TITLE,
} from '../constants';
import type { IbkrMode } from '../ibkr/types';

export type StockViewOperatorMode = 'manual' | 'normal' | 'fully_automated';

/** Placeholder until Manual / Fully Automated are wired; Normal is the only live option. */
const OPERATOR_MODE: StockViewOperatorMode = 'normal';

export function StockViewOperatorModeCapsule() {
  return (
    <div
      className="sv-capsule sv-capsule--mode"
      role="group"
      aria-label="Operator mode"
      data-testid="sv-operator-mode-capsule"
    >
      <button
        type="button"
        className="sv-capsule__seg"
        disabled
        aria-pressed={OPERATOR_MODE === 'manual'}
        title={STOCK_VIEW_OPERATOR_MODE_MANUAL_TITLE}
      >
        {STOCK_VIEW_OPERATOR_MODE_MANUAL}
      </button>
      <button
        type="button"
        className={`sv-capsule__seg${OPERATOR_MODE === 'normal' ? ' is-selected' : ''}`}
        aria-pressed={OPERATOR_MODE === 'normal'}
        title={STOCK_VIEW_OPERATOR_MODE_NORMAL_TITLE}
      >
        {STOCK_VIEW_OPERATOR_MODE_NORMAL}
      </button>
      <button
        type="button"
        className="sv-capsule__seg"
        disabled
        aria-pressed={OPERATOR_MODE === 'fully_automated'}
        title={STOCK_VIEW_OPERATOR_MODE_FULL_AUTO_TITLE}
      >
        {STOCK_VIEW_OPERATOR_MODE_FULL_AUTO}
      </button>
    </div>
  );
}

interface AccountModeProps {
  mode: IbkrMode;
}

export function StockViewAccountModeCapsule({ mode }: AccountModeProps) {
  const selected = mode === 'live' ? 'live' : mode === 'paper' ? 'paper' : null;

  function requestMode(next: 'paper' | 'live') {
    if (next === selected) return;
    const message =
      next === 'live'
        ? STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE
        : STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE;
    window.confirm(message);
  }

  return (
    <div
      className="sv-capsule sv-capsule--account"
      role="group"
      aria-label="Account mode"
      data-testid="sv-account-mode-capsule"
    >
      <button
        type="button"
        className={`sv-capsule__seg${selected === 'paper' ? ' is-selected is-paper' : ''}`}
        aria-pressed={selected === 'paper'}
        disabled={mode === 'disconnected'}
        title={STOCK_VIEW_ACCOUNT_MODE_PAPER_TITLE}
        onClick={() => requestMode('paper')}
      >
        {STOCK_VIEW_ACCOUNT_MODE_PAPER}
      </button>
      <button
        type="button"
        className={`sv-capsule__seg${selected === 'live' ? ' is-selected is-live' : ''}`}
        aria-pressed={selected === 'live'}
        disabled={mode === 'disconnected'}
        title={STOCK_VIEW_ACCOUNT_MODE_LIVE_TITLE}
        onClick={() => requestMode('live')}
      >
        {STOCK_VIEW_ACCOUNT_MODE_LIVE}
      </button>
    </div>
  );
}

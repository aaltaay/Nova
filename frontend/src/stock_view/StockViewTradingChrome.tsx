/** Stock View header capsules — operator mode, Paper/Live.
 * Paper/Live is the shared GatewayModeCapsule (header + Stock View). */
import {
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO,
  STOCK_VIEW_OPERATOR_MODE_FULL_AUTO_TITLE,
  STOCK_VIEW_OPERATOR_MODE_MANUAL,
  STOCK_VIEW_OPERATOR_MODE_MANUAL_TITLE,
  STOCK_VIEW_OPERATOR_MODE_NORMAL,
  STOCK_VIEW_OPERATOR_MODE_NORMAL_TITLE,
} from '../constants';
import {
  GatewayModeCapsule,
  type GatewayModeCapsuleProps,
} from '../ibkr/GatewayModeCapsule';

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

export function StockViewAccountModeCapsule(props: GatewayModeCapsuleProps) {
  return (
    <GatewayModeCapsule
      {...props}
      testId="sv-account-mode-capsule"
      errorTestId="sv-account-mode-error"
    />
  );
}

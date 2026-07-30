/**
 * Settings > Trade > Order Preferences.
 */
import { useState } from 'react';
import {
  TRADE_ORDER_PREFS_SKIP_CONFIRM_HINT,
  TRADE_ORDER_PREFS_SKIP_CONFIRM_LABEL,
} from '../constantGroups/trade_defaults';
import {
  readSkipPlaceConfirm,
  writeSkipPlaceConfirm,
} from '../ibkr/placeConfirmPrefs';

export function TradeOrderPreferencesForm() {
  const [skipConfirm, setSkipConfirm] = useState(readSkipPlaceConfirm);

  return (
    <div
      className="trade-order-prefs-form"
      data-testid="trade-order-preferences"
    >
      <label className="trade-prefs-check">
        <input
          type="checkbox"
          checked={skipConfirm}
          onChange={(e) => {
            const next = e.target.checked;
            writeSkipPlaceConfirm(next);
            setSkipConfirm(next);
          }}
        />
        <span>
          <strong>{TRADE_ORDER_PREFS_SKIP_CONFIRM_LABEL}</strong>
          <span className="settings-block-hint">
            {TRADE_ORDER_PREFS_SKIP_CONFIRM_HINT}
          </span>
        </span>
      </label>
    </div>
  );
}

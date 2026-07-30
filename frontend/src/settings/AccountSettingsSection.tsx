/**
 * Settings > Account — IBKR status summary + open Trading tab.
 */
import {
  SETTINGS_ACCOUNT_DISCONNECTED,
  SETTINGS_ACCOUNT_OPEN_TRADING,
  SETTINGS_ACCOUNT_TITLE,
} from '../constantGroups/trade_defaults';
import { requestOpenTradingTab } from '../components/openTradingTabNav';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';

interface Props {
  onClose: () => void;
}

export function AccountSettingsSection({ onClose }: Props) {
  const status = useIbkrStatus();
  const modeLabel =
    status.mode === 'paper'
      ? 'Paper'
      : status.mode === 'live'
        ? 'Live'
        : 'Disconnected';

  return (
    <div className="settings-account" data-testid="settings-account">
      <h3 className="settings-block-title">{SETTINGS_ACCOUNT_TITLE}</h3>
      <dl className="settings-account-dl">
        <div>
          <dt>Connection</dt>
          <dd>
            {status.connected
              ? `Connected (${modeLabel})`
              : SETTINGS_ACCOUNT_DISCONNECTED}
          </dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd>{modeLabel}</dd>
        </div>
        {status.spend_status != null && status.spend_status !== '' && (
          <div>
            <dt>Orders</dt>
            <dd>{status.spend_status}</dd>
          </div>
        )}
      </dl>
      <button
        type="button"
        className="settings-account-open-trading"
        onClick={() => {
          requestOpenTradingTab();
          onClose();
        }}
      >
        {SETTINGS_ACCOUNT_OPEN_TRADING}
      </button>
    </div>
  );
}

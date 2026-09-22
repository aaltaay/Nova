/**
 * Settings > Account — IBKR status summary + a door to the Account page.
 *
 * Orders reads the spend state in words (spendLock.spendStatusLabel), never
 * the raw token (`locked_disarmed`), and the button opens the rail's Account
 * page rather than the legacy Trading tab (QA V35, 2026-09-22). Mode is the
 * status's own venue (ADR 020), so the by-hand paper Gateway on Live reads Live.
 */
import { SENSORS_ACCOUNT_HINT } from '../constantGroups/sensors';
import {
  SETTINGS_ACCOUNT_DISCONNECTED,
  SETTINGS_ACCOUNT_OPEN_ACCOUNT,
  SETTINGS_ACCOUNT_OPEN_ACCOUNT_TITLE,
  SETTINGS_ACCOUNT_TITLE,
  SETTINGS_ACCOUNT_VENUE_LABELS,
} from '../constantGroups/trade_defaults';
import { deskVenueOf } from '../ibkr/deskVenue';
import { spendStatusLabel } from '../ibkr/spendLock';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { setNavPage } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';

interface Props {
  onClose: () => void;
}

export function AccountSettingsSection({ onClose }: Props) {
  const status = useIbkrStatus();
  const { traderViewActive, showScannerView } = useWorkspace();
  const venue = deskVenueOf(status);
  const modeLabel = venue ? SETTINGS_ACCOUNT_VENUE_LABELS[venue] : SETTINGS_ACCOUNT_DISCONNECTED;
  const spend = typeof status.spend_status === 'string' && status.spend_status ? status.spend_status : null;

  return (
    <div className="settings-account" data-testid="settings-account">
      <h3 className="settings-block-title">{SETTINGS_ACCOUNT_TITLE}</h3>
      <p className="settings-block-hint">
        {SENSORS_ACCOUNT_HINT}
      </p>
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
        {spend && (
          <div>
            <dt>Orders</dt>
            <dd data-testid="settings-account-orders" title={spend}>{spendStatusLabel(spend)}</dd>
          </div>
        )}
      </dl>
      <button
        type="button"
        className="btn-secondary settings-account-open-trading"
        data-testid="settings-account-open-account"
        title={SETTINGS_ACCOUNT_OPEN_ACCOUNT_TITLE}
        onClick={() => {
          if (traderViewActive) showScannerView();
          setNavPage('account');
          onClose();
        }}
      >
        {SETTINGS_ACCOUNT_OPEN_ACCOUNT}
      </button>
    </div>
  );
}

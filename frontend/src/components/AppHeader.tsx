/**
 * AppHeader — brand, market mode, connection/feed/scan-age meta, lookup, settings.
 * Extracted from App.tsx so the header stays modular and the tab bar stays tabs-only.
 */
import type { ChangeEvent } from 'react';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { SymbolSearchBox } from './SymbolSearchBox';
import { ThemeToggle } from './ThemeToggle';
import {
  ACCOUNT_NAV_LABEL,
  ACCOUNT_NAV_TITLE,
  DISCOVERY_PROVIDER_DEFAULT,
  SAMPLE_DATA_SWITCH_LABEL,
} from '../constants';
import type { IbkrMode } from '../ibkr/types';
import type { HealthStatus } from '../types/health';

export type MarketMode = 'premarket' | 'market' | 'afterhours' | 'closed' | 'loading';

const MODE_LABELS: Record<MarketMode, string> = {
  loading: 'Connecting…',
  premarket: 'Pre-Market',
  market: 'Market Hours',
  afterhours: 'After Hours',
  closed: 'Market Closed',
};

function NovaLogo() {
  return (
    <svg
      className="nova-logo"
      xmlns="http://www.w3.org/2000/svg"
      width="40"
      height="38"
      fill="none"
      viewBox="0 0 48 46"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M25.946 44.938c-.664.845-2.021.375-2.021-.698V33.937a2.26 2.26 0 0 0-2.262-2.262H10.287c-.92 0-1.456-1.04-.92-1.788l7.48-10.471c1.07-1.497 0-3.578-1.842-3.578H1.237c-.92 0-1.456-1.04-.92-1.788L10.013.474c.214-.297.556-.474.92-.474h28.894c.92 0 1.456 1.04.92 1.788l-7.48 10.471c-1.07 1.498 0 3.579 1.842 3.579h11.377c.943 0 1.473 1.088.89 1.83L25.947 44.94z"
      />
    </svg>
  );
}

function fmtHistoryDate(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

interface Props {
  mode: MarketMode;
  health: HealthStatus;
  activeFeed: string;
  feedFellBack: boolean;
  /** Live scan age in seconds; null when unknown or viewing history. */
  secondsAgo: number | null;
  /** True when IBKR table price ticks are late — show warning color, never hide. */
  pricesStale?: boolean;
  /** IB Gateway API session (separate from Nova API health). */
  ibkrConnected?: boolean;
  /** paper | live | disconnected — must appear on the Gateway chip. */
  ibkrMode?: IbkrMode;
  ibkrGatewayMode?: 'paper' | 'live' | null;
  historyDate: string | null;
  historyDates: string[];
  onHistoryChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onLookup: (symbol: string) => void;
  showSettings: boolean;
  onToggleSettings: () => void;
  /** Compact header for ticker-detail full page (no lookup / history / settings). */
  compact?: boolean;
  /** Show scanner source badge (hide on Account view). */
  showScannerSource?: boolean;
  /** Scanner discovery provider — product path is always 'ibkr'. */
  discoveryProvider?: string;
  /** After Start API succeeds — refresh scanner/health. */
  onBackendStarted?: () => void;
  /** Account control next to Today (Live). */
  accountActive?: boolean;
  onAccountClick?: () => void;
  /** Isolated sample-data route toggle (?view=sample) — never mixes with live. */
  sampleDataActive?: boolean;
  onSampleDataToggle?: (active: boolean) => void;
}

export function AppHeader({
  mode,
  health,
  activeFeed,
  feedFellBack,
  secondsAgo,
  pricesStale = false,
  ibkrConnected = false,
  ibkrMode = 'disconnected',
  ibkrGatewayMode = null,
  historyDate,
  historyDates,
  onHistoryChange,
  onLookup,
  showSettings,
  onToggleSettings,
  compact = false,
  showScannerSource = true,
  discoveryProvider = DISCOVERY_PROVIDER_DEFAULT,
  onBackendStarted,
  accountActive = false,
  onAccountClick,
  sampleDataActive = false,
  onSampleDataToggle,
}: Props) {
  return (
    <header className={compact ? 'app-header app-header--compact' : 'app-header'}>
      <div className="header-brand">
        <div className="brand">
          <NovaLogo />
          <div className="brand-text">
            <span className="brand-wordmark">NOVA</span>
            <span className="brand-tagline">
              {sampleDataActive ? 'Sample Scanner' : 'Stock Scanner'}
            </span>
          </div>
        </div>
        <span className={`mode-badge mode-${mode}`}>
          {sampleDataActive ? 'Sample data' : MODE_LABELS[mode]}
        </span>
        <ThemeToggle />
      </div>

      <div className="header-status" aria-live="polite">
        <HeaderConnectionStatus
          health={health}
          discoveryProvider={discoveryProvider}
          ibkrConnected={ibkrConnected}
          ibkrMode={ibkrMode}
          ibkrGatewayMode={ibkrGatewayMode}
          activeFeed={activeFeed}
          feedFellBack={feedFellBack}
          secondsAgo={secondsAgo}
          pricesStale={pricesStale}
          historyDate={historyDate}
          compact={compact}
          showScannerSource={showScannerSource}
          onBackendStarted={onBackendStarted}
        />
      </div>

      {!compact && (
        <div className="header-actions">
          {onSampleDataToggle && (
            <label
              className={`sample-data-switch${sampleDataActive ? ' sample-data-switch--on' : ''}`}
              title="Open isolated sample fixtures — never mixed with live market data"
              data-testid="sample-data-switch"
            >
              <input
                type="checkbox"
                checked={sampleDataActive}
                onChange={(e) => onSampleDataToggle(e.target.checked)}
              />
              <span>{SAMPLE_DATA_SWITCH_LABEL}</span>
            </label>
          )}
          <select
            className={`history-select${historyDate ? ' history-select--active' : ''}`}
            value={historyDate ?? ''}
            onChange={onHistoryChange}
            title="Browse historical snapshots"
            disabled={sampleDataActive}
          >
            <option value="">{sampleDataActive ? 'Sample (fixtures)' : 'Today (Live)'}</option>
            {!sampleDataActive &&
              historyDates.map(d => (
                <option key={d} value={d}>{fmtHistoryDate(d)}</option>
              ))}
          </select>
          {onAccountClick && (
            <button
              type="button"
              className={`account-nav-btn${accountActive ? ' active' : ''}`}
              title={ACCOUNT_NAV_TITLE}
              aria-pressed={accountActive}
              data-testid="header-account-btn"
              onClick={onAccountClick}
            >
              {ACCOUNT_NAV_LABEL}
            </button>
          )}
          <SymbolSearchBox onLookup={onLookup} />
          <button
            className={`settings-btn ${showSettings ? 'active' : ''}`}
            onClick={onToggleSettings}
            type="button"
          >
            Settings
          </button>
        </div>
      )}
    </header>
  );
}

/** Re-export for history banner formatting in App. */
export { fmtHistoryDate };

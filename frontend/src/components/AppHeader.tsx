/**
 * AppHeader — brand, market mode, connection/feed/scan-age meta, lookup, settings.
 * Extracted from App.tsx so the header stays modular and the tab bar stays tabs-only.
 */
import type { ChangeEvent } from 'react';
import { SymbolSearchBox } from './SymbolSearchBox';
import {
  DATA_FEED_LABELS,
  DISCOVERY_PROVIDER_DEFAULT,
  SCANNER_DATA_SOURCE_LABELS,
  SCANNER_DATA_SOURCE_TITLES,
} from '../constants';

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
      <defs>
        <linearGradient id="nova-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#863bff" />
          <stop offset="100%" stopColor="#47bfff" />
        </linearGradient>
      </defs>
      <path
        fill="url(#nova-grad)"
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

function dotClass(status: string): string {
  if (status === 'connected') return 'connected';
  if (status === 'disconnected') return 'disconnected';
  return 'loading';
}

interface HealthProps {
  status: string;
  latency_ms: number;
  message?: string;
}

interface Props {
  mode: MarketMode;
  health: HealthProps;
  activeFeed: string;
  feedFellBack: boolean;
  /** Live scan age in seconds; null when unknown or viewing history. */
  secondsAgo: number | null;
  historyDate: string | null;
  historyDates: string[];
  onHistoryChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onLookup: (symbol: string) => void;
  showSettings: boolean;
  onToggleSettings: () => void;
  /** Compact header for ticker-detail full page (no lookup / history / settings). */
  compact?: boolean;
  /** Show scanner source badge (hide on Trading tab). */
  showScannerSource?: boolean;
  /** Which provider sources gappers/gainers/losers ('alpaca' or 'ibkr'). */
  discoveryProvider?: string;
}

export function AppHeader({
  mode,
  health,
  activeFeed,
  feedFellBack,
  secondsAgo,
  historyDate,
  historyDates,
  onHistoryChange,
  onLookup,
  showSettings,
  onToggleSettings,
  compact = false,
  showScannerSource = true,
  discoveryProvider = DISCOVERY_PROVIDER_DEFAULT,
}: Props) {
  return (
    <header className={compact ? 'app-header app-header--compact' : 'app-header'}>
      <div className="header-brand">
        <div className="brand">
          <NovaLogo />
          <div className="brand-text">
            <span className="brand-wordmark">NOVA</span>
            <span className="brand-tagline">Stock Scanner</span>
          </div>
        </div>
        <span className={`mode-badge mode-${mode}`}>{MODE_LABELS[mode]}</span>
      </div>

      <div className="header-status" aria-live="polite">
        <div className="status-indicator">
          <span className={`dot ${dotClass(health.status)}`} />
          <span style={{ textTransform: 'capitalize' }}>{health.status}</span>
          {health.latency_ms > 0 && <span>({health.latency_ms}ms)</span>}
          <span
            className={`feed-badge feed-${activeFeed}`}
            title={`Data feed: ${DATA_FEED_LABELS[activeFeed] || activeFeed.toUpperCase()}`}
          >
            {activeFeed.toUpperCase()}
          </span>
          {feedFellBack && (
            <span
              className="feed-fallback-hint"
              title="SIP feed was rejected; automatically fell back to IEX. Change in Settings if your plan supports SIP."
            >
              ⚠ fallback
            </span>
          )}
          {!compact && !historyDate && secondsAgo != null && (
            <>
              <span className="header-meta-sep" aria-hidden="true">·</span>
              <span className="scan-age">updated {secondsAgo}s ago</span>
            </>
          )}
          {!compact && showScannerSource && (
            <>
              <span className="header-meta-sep" aria-hidden="true">·</span>
              <span
                className="header-data-source"
                title={SCANNER_DATA_SOURCE_TITLES[discoveryProvider] || SCANNER_DATA_SOURCE_TITLES[DISCOVERY_PROVIDER_DEFAULT]}
              >
                {SCANNER_DATA_SOURCE_LABELS[discoveryProvider] || SCANNER_DATA_SOURCE_LABELS[DISCOVERY_PROVIDER_DEFAULT]}
              </span>
            </>
          )}
          {health.message && health.status !== 'connected' && (
            <span className="status-hint" title={health.message}>
              {' '}— {health.message.length > 80 ? `${health.message.slice(0, 80)}…` : health.message}
            </span>
          )}
        </div>
      </div>

      {!compact && (
        <div className="header-actions">
          <select
            className={`history-select${historyDate ? ' history-select--active' : ''}`}
            value={historyDate ?? ''}
            onChange={onHistoryChange}
            title="Browse historical snapshots"
          >
            <option value="">Today (Live)</option>
            {historyDates.map(d => (
              <option key={d} value={d}>{fmtHistoryDate(d)}</option>
            ))}
          </select>
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

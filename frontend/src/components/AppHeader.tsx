/**
 * Scanner status chrome — market mode, connection pills, history, symbol lookup.
 * Live Scanner portals this above GlobalAppBar (no homepage brand block).
 */
import { useLayoutEffect, useState, type ChangeEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { SCANNER_STATUS_SLOT_ID } from './scannerStatusSlot';
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
  /** Compact header for ticker-detail full page (no lookup / history). */
  compact?: boolean;
  /** Show scanner source badge (hide on Account view). */
  showScannerSource?: boolean;
  /** Scanner discovery provider — product path is always 'ibkr'. */
  discoveryProvider?: string;
  /** After Start API succeeds — refresh scanner/health. */
  onBackendStarted?: () => void;
  /** Sample shell only — live Account lives on GlobalAppBar. */
  accountActive?: boolean;
  onAccountClick?: () => void;
  /** Isolated sample-data route toggle (?view=sample) — never mixes with live. */
  sampleDataActive?: boolean;
  onSampleDataToggle?: (active: boolean) => void;
  /**
   * When true, render into `#nova-scanner-status-slot` above GlobalAppBar.
   * Sample shell keeps inline (no slot).
   */
  portalToTop?: boolean;
}

function useStatusSlot(enabled: boolean): HTMLElement | null {
  const [slot, setSlot] = useState<HTMLElement | null>(() =>
    enabled && typeof document !== 'undefined'
      ? document.getElementById(SCANNER_STATUS_SLOT_ID)
      : null,
  );

  useLayoutEffect(() => {
    if (!enabled) {
      setSlot(null);
      return;
    }
    setSlot(document.getElementById(SCANNER_STATUS_SLOT_ID));
  }, [enabled]);

  return slot;
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
  compact = false,
  showScannerSource = true,
  discoveryProvider = DISCOVERY_PROVIDER_DEFAULT,
  onBackendStarted,
  accountActive = false,
  onAccountClick,
  sampleDataActive = false,
  onSampleDataToggle,
  portalToTop = false,
}: Props) {
  const slot = useStatusSlot(portalToTop);

  const body: ReactNode = (
    <header
      className={[
        'app-header',
        'app-header--status-chrome',
        compact ? 'app-header--compact' : '',
        portalToTop ? 'app-header--top-chrome' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      data-testid="scanner-status-chrome"
    >
      <div className="header-leading">
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
              historyDates.map((d) => (
                <option key={d} value={d}>
                  {fmtHistoryDate(d)}
                </option>
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
        </div>
      )}
    </header>
  );

  if (portalToTop && slot) {
    return createPortal(body, slot);
  }
  return body;
}

/** Re-export for history banner formatting in App. */
export { fmtHistoryDate };

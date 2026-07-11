import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { HodMomoTab } from './hod_momo/HodMomoTab';
import { HodMomoSettings } from './hod_momo/HodMomoSettings';
import { useHodMomoStream } from './hod_momo/useHodMomoStream';
import { useHodMomoConfig } from './hod_momo/useHodMomoConfig';
import { TabNav } from './components/TabNav';
import type { ActiveTab } from './components/TabNav';
import { AppHeader, fmtHistoryDate } from './components/AppHeader';
import type { MarketMode } from './components/AppHeader';
import { SidePanel } from './components/SidePanel';
import { SymbolSelectButton } from './components/SymbolSelectButton';
import type { NewsImpactVerdict } from './types/newsImpact';
import { TradingTab } from './ibkr/TradingTab';
import { WatchlistTab } from './strategy/WatchlistTab';
import { useWatchlist } from './strategy/useWatchlist';
import { ReportsTab } from './reports/ReportsTab';
import { TickerDetailPage } from './pages/TickerDetailPage';
import { fmtMarketCap, fmtPct, fmtPrice, fmtVolume } from './utils/quoteFormat';
import {
  SMALL_CAP_MIN, SMALL_CAP_MAX,
  NEWS_FLAME_HOT_HOURS, NEWS_FLAME_WARM_HOURS, NEWS_FLAME_MAX_HOURS,
  GAPPER_MIN_GAP_PCT,
  SCANNER_COLUMNS,
  DATA_FEED_DEFAULT,
  DATA_FEED_LABELS,
  API_BASE_URL,
  NEWS_IMPACT_CLASS_LABELS,
  NEWS_IMPACT_CLASS_TOOLTIPS,
} from './constants';
import { isNovaApiDebug } from './debug';

type Mode = MarketMode;
// ActiveTab is imported from components/TabNav — includes 'trading'
type SortDir = 'asc' | 'desc' | null;
interface SortConfig { key: string; dir: SortDir; }

interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
}

interface ScannerRow {
  symbol: string;
  price: number;
  prev_close: number;
  change_pct: number;
  change_abs: number;
  gap_percent: number | null;
  volume: number;
  rel_volume: number | null;
  has_news: boolean;
  newest_headline_at: string | null;
  market_cap: number | null;
  float: number | null;
  short_interest: number | null;
  short_ratio: number | null;
}

// Legacy aliases — kept for any remaining narrower references
type Gapper    = ScannerRow;
type Mover     = ScannerRow;
type Afterhours = ScannerRow;

interface Catalyst {
  symbol: string;
  previous_close: number;
  current_price: number;
  gap_percent: number;
  volume: number;
  has_news: boolean;
  newest_headline_at: string | null;
  catalyst_headline: string | null;
  catalyst_url: string | null;
  news_impact?: NewsImpactVerdict | null;
}

// Scanner formatters imported from utils/quoteFormat

function NewsCell({ newest_headline_at }: { newest_headline_at: string | null }) {
  if (!newest_headline_at) return <span className="na-muted">—</span>;
  const ageHours = (Date.now() - new Date(newest_headline_at).getTime()) / 3_600_000;
  if (ageHours > NEWS_FLAME_MAX_HOURS) return <span className="na-muted">—</span>;
  let colorClass: string;
  if (ageHours <= NEWS_FLAME_HOT_HOURS) colorClass = 'flame-hot';
  else if (ageHours <= NEWS_FLAME_WARM_HOURS) colorClass = 'flame-warm';
  else colorClass = 'flame-cool';
  const label = ageHours < 1 ? `${Math.round(ageHours * 60)}m ago` : `${Math.floor(ageHours)}h ago`;
  return <span className={`news-flame ${colorClass}`} title={label} />;
}

function EmptyState({
  health,
  context,
}: {
  health: HealthStatus;
  context: Mode;
}) {
  // Still waiting for first API response
  if (context === 'loading') {
    return <div className="empty-state">Loading market data…</div>;
  }
  // Mode is known — show the right message regardless of health ping state
  if (health.status === 'disconnected' || health.status === 'error') {
    return (
      <div className="empty-state">
        {health.message || 'Check API keys in Settings.'}
      </div>
    );
  }
  if (context === 'closed') {
    return (
      <div className="empty-state">
        Market is closed — showing last available data. Scanning continues in the background.
      </div>
    );
  }
  if (context === 'premarket') {
    return (
      <div className="empty-state">
        No gappers with a gap of at least {GAPPER_MIN_GAP_PCT}% yet — scan running…
      </div>
    );
  }
  if (context === 'afterhours') {
    return (
      <div className="empty-state">
        No after-hours movers with a gap of at least {GAPPER_MIN_GAP_PCT}% yet — scan running…
      </div>
    );
  }
  return <div className="empty-state">No gainers in the feed right now.</div>;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_URL = `${API_BASE_URL}/api`;

// ── Scanner Table ─────────────────────────────────────────────────────────────

interface ScannerTableProps {
  columns: [string, string][];
  data: ScannerRow[];
  sortState: SortConfig;
  onSort: (key: string) => void;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

function renderCell(key: string, row: ScannerRow): React.ReactNode {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyRow = row as any;
  switch (key) {
    case 'symbol':
      return null; // handled as the symbol button in the row
    case 'price':
      return fmtPrice(row.price ?? anyRow.current_price);
    case 'prev_close':
      return fmtPrice(row.prev_close ?? anyRow.previous_close);
    case 'change_pct':
      return (
        <span className={row.change_pct != null && row.change_pct >= 0 ? 'positive' : 'negative'}>
          {fmtPct(row.change_pct)}
        </span>
      );
    case 'change_abs':
      return (
        <span className={row.change_abs != null && row.change_abs >= 0 ? 'positive' : 'negative'}>
          {row.change_abs != null ? `${row.change_abs >= 0 ? '+' : ''}${row.change_abs.toFixed(2)}` : '—'}
        </span>
      );
    case 'gap_percent':
      return (
        <span className={row.gap_percent != null && row.gap_percent >= 0 ? 'positive' : row.gap_percent != null ? 'negative' : ''}>
          {fmtPct(row.gap_percent)}
        </span>
      );
    case 'volume':
      return fmtVolume(row.volume);
    case 'rel_volume':
      return row.rel_volume != null
        ? `${row.rel_volume}x`
        : <span className="na-muted">N/A</span>;
    case 'newest_headline_at':
      return <NewsCell newest_headline_at={row.newest_headline_at} />;
    case 'market_cap':
      return row.market_cap != null ? fmtMarketCap(row.market_cap) : <span className="na-muted">—</span>;
    case 'float':
      return row.float != null ? fmtVolume(row.float) : <span className="na-muted">—</span>;
    case 'short_interest':
      return row.short_interest != null ? fmtVolume(row.short_interest) : <span className="na-muted">—</span>;
    case 'short_ratio':
      return row.short_ratio != null ? row.short_ratio.toFixed(1) : <span className="na-muted">—</span>;
    default:
      return <span className="na-muted">—</span>;
  }
}

function ScannerTable({
  columns, data, sortState, onSort, selectedSymbol, onSelect, onOpenTrading,
}: ScannerTableProps) {
  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            {columns.map(([key, label]) => (
              <th
                key={key}
                className="sortable-th"
                onClick={() => onSort(key)}
                aria-sort={
                  sortState.key === key
                    ? sortState.dir === 'asc' ? 'ascending' : 'descending'
                    : 'none'
                }
              >
                <span className="th-inner">
                  {label}
                  <span className={`sort-arrow${sortState.key === key ? ' active' : ''}`}>
                    {sortState.key === key
                      ? sortState.dir === 'asc' ? '↑' : '↓'
                      : '↕'}
                  </span>
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map(row => (
            <tr key={row.symbol} className={selectedSymbol === row.symbol ? 'row-selected' : ''}>
              {columns.map(([key]) =>
                key === 'symbol' ? (
                  <td key={key}>
                    <SymbolSelectButton
                      symbol={row.symbol}
                      selected={selectedSymbol === row.symbol}
                      onSelect={onSelect}
                      onOpenTrading={onOpenTrading}
                    />
                  </td>
                ) : (
                  <td key={key}>{renderCell(key, row)}</td>
                )
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

function App() {
  const [mode, setMode] = useState<Mode>('loading');
  const [health, setHealth] = useState<HealthStatus>({ status: 'loading', latency_ms: 0 });
  const [gappers, setGappers] = useState<Gapper[]>([]);
  const [movers, setMovers] = useState<Mover[]>([]);
  const [afterhours, setAfterhours] = useState<Afterhours[]>([]);
  const [lastScan, setLastScan] = useState<number>(0);
  const [showSettings, setShowSettings] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [activeTab, setActiveTab] = useState<ActiveTab>('gappers');
  // Polls continuously (cheap — scored from already-cached scanner data) so the
  // tab badge count stays accurate even when the Watchlist tab isn't open.
  const watchlist = useWatchlist(true);
  const [showHodSettings, setShowHodSettings] = useState(false);
  const [tabOverridden, setTabOverridden] = useState(false);
  const [gapperSubTab, setGapperSubTab] = useState<'all' | 'small_cap'>('all');
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [moverSort, setMoverSort] = useState<SortConfig>({ key: '', dir: null });
  const [afterhoursSort, setAfterhoursSort] = useState<SortConfig>({ key: '', dir: null });
  const [catalystSort, setCatalystSort] = useState<SortConfig>({ key: '', dir: null });

  // Catalysts tab state
  const [catalysts, setCatalysts] = useState<Catalyst[]>([]);

  // selectedSymbol → side panel only; tradingSymbol → full trading page (double-click)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tradingSymbol, setTradingSymbol] = useState<string | null>(null);

  const openTradingView = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setSelectedSymbol(sym);
    setTradingSymbol(sym);
  }, []);

  // Settings form state
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.alpaca.markets');
  const [dataFeed, setDataFeed] = useState(DATA_FEED_DEFAULT);
  const [dataFeedOptions, setDataFeedOptions] = useState<string[]>(['iex', 'sip']);
  const [feedFellBack, setFeedFellBack] = useState(false);
  const [activeFeed, setActiveFeed] = useState(DATA_FEED_DEFAULT);

  // History / time-travel state
  const [historyDate, setHistoryDate] = useState<string | null>(null); // null = live
  const [historyDates, setHistoryDates] = useState<string[]>([]);

  // HOD Momo Scanner
  const hodMomoStream = useHodMomoStream();
  const hodMomoConfig = useHodMomoConfig();

  function toggleSort<T extends SortConfig>(
    current: T,
    setter: (s: SortConfig) => void,
    key: string,
  ) {
    if (current.key !== key) setter({ key, dir: 'asc' });
    else if (current.dir === 'asc') setter({ key, dir: 'desc' });
    else if (current.dir === 'desc') setter({ key: '', dir: null });
    else setter({ key, dir: 'asc' });
  }

  function sortedArray<T>(arr: T[], cfg: SortConfig): T[] {
    if (!cfg.key || !cfg.dir) return arr;
    const { key, dir } = cfg;
    return [...arr].sort((a, b) => {
      const av = (a as Record<string, unknown>)[key] ?? null;
      const bv = (b as Record<string, unknown>)[key] ?? null;
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      let cmp = 0;
      if (typeof av === 'number' && typeof bv === 'number') {
        cmp = av - bv;
      } else {
        cmp = String(av).localeCompare(String(bv));
      }
      return dir === 'asc' ? cmp : -cmp;
    });
  }

  const sortedGappers = useMemo(
    () => sortedArray(gappers, gapperSort),
    [gappers, gapperSort],
  );

  const smallCapGappers = useMemo(
    () => gappers.filter(g =>
      g.market_cap != null &&
      g.market_cap >= SMALL_CAP_MIN &&
      g.market_cap < SMALL_CAP_MAX
    ),
    [gappers],
  );

  const sortedSmallCapGappers = useMemo(
    () => sortedArray(smallCapGappers, gapperSort),
    [smallCapGappers, gapperSort],
  );

  const sortedMovers = useMemo(
    () => sortedArray(movers, moverSort),
    [movers, moverSort],
  );

  const sortedAfterhours = useMemo(
    () => sortedArray(afterhours, afterhoursSort),
    [afterhours, afterhoursSort],
  );

  const sortedCatalysts = useMemo(
    () => sortedArray(catalysts, catalystSort),
    [catalysts, catalystSort],
  );

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/config`);
      if (res.ok) {
        const data = await res.json();
        setApiKey(data.api_key);
        setApiSecret(data.api_secret);
        setBaseUrl(data.base_url);
        if (data.data_feed) {
          setDataFeed(data.data_feed);
          setActiveFeed(data.data_feed);
        }
        if (Array.isArray(data.data_feed_options)) setDataFeedOptions(data.data_feed_options);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const [gr, moversRes, ahRes, catalystRes] = await Promise.all([
        fetch(`${API_URL}/gappers`),
        fetch(`${API_URL}/movers`),
        fetch(`${API_URL}/afterhours`),
        fetch(`${API_URL}/news-catalysts`),
      ]);

      if (gr.ok) {
        const data = await gr.json();
        if (data.health) {
          setHealth(data.health);
          if (data.health.feed_fell_back != null) setFeedFellBack(data.health.feed_fell_back);
        }
        if (data.mode) setMode(data.mode as Mode);
        if (data.data_feed) setActiveFeed(data.data_feed);
        if (Array.isArray(data.gappers)) setGappers(data.gappers);
        if (data.last_scan) setLastScan(data.last_scan);
      }

      if (moversRes.ok) {
        const data = await moversRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) setLastScan(data.last_scan);
        const gainers: Mover[] = Array.isArray(data.gainers) ? data.gainers : [];
        const losers: Mover[] = Array.isArray(data.losers) ? data.losers : [];
        setMovers([...gainers, ...losers]);
      }

      if (ahRes.ok) {
        const data = await ahRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) setLastScan(data.last_scan);
        if (Array.isArray(data.afterhours)) setAfterhours(data.afterhours);
      }

      if (catalystRes.ok) {
        const data = await catalystRes.json();
        if (Array.isArray(data.catalysts)) setCatalysts(data.catalysts);
      }

      if (isNovaApiDebug()) {
        for (const [label, res] of [
          ['gappers', gr],
          ['movers', moversRes],
          ['afterhours', ahRes],
          ['catalysts', catalystRes],
        ] as const) {
          if (!res.ok) {
            console.warn(`[Nova] GET ${API_URL}/${label} -> HTTP ${res.status}`, res.statusText);
          }
        }
      }
    } catch (e) {
      console.error('[Nova] Scanner API network error', {
        API_URL,
        API_BASE_URL,
        hint: 'Backend root / returns 404 by design. Test: ' + `${API_BASE_URL}/api/health`,
        trace: isNovaApiDebug() ? e : '(set localStorage novaApiDebug=1 and reload for details)',
      });
      if (isNovaApiDebug()) {
        console.info(
          '[Nova] F12 → Network: find failed request to /api/gappers. Console: localStorage.setItem("novaApiDebug","1") then reload.',
        );
      }
      setHealth({ status: 'disconnected', latency_ms: 0, message: 'Backend unreachable' });
    }
  }, []);

  const fetchHistoryDates = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/history/dates?type=gappers`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.dates)) setHistoryDates(data.dates);
      }
    } catch {
      // silent — history dropdown just stays empty
    }
  }, []);

  const fetchHistoryData = useCallback(async (date: string) => {
    try {
      const [gr, moversRes, ahRes] = await Promise.all([
        fetch(`${API_URL}/history/gappers/${date}`),
        fetch(`${API_URL}/history/movers/${date}`),
        fetch(`${API_URL}/history/afterhours/${date}`),
      ]);
      if (gr.ok) {
        const data = await gr.json();
        if (Array.isArray(data.gappers)) setGappers(data.gappers);
        else setGappers([]);
      }
      if (moversRes.ok) {
        const data = await moversRes.json();
        const gainers: Mover[] = Array.isArray(data.gainers) ? data.gainers : [];
        const losers: Mover[] = Array.isArray(data.losers) ? data.losers : [];
        setMovers([...gainers, ...losers]);
      }
      if (ahRes.ok) {
        const data = await ahRes.json();
        if (Array.isArray(data.afterhours)) setAfterhours(data.afterhours);
        else setAfterhours([]);
      }
    } catch {
      // silent
    }
  }, []);

  // Auto-switch tab when mode changes, unless user has manually picked a tab
  useEffect(() => {
    if (!tabOverridden) {
      if (mode === 'market') setActiveTab('movers');
      else if (mode === 'afterhours') setActiveTab('afterhours');
      else setActiveTab('gappers');
    }
  }, [mode, tabOverridden]);

  // Live poll — only runs when not in history mode
  useEffect(() => {
    fetchConfig();
    fetchHistoryDates();
    if (historyDate !== null) return; // history mode: no polling
    fetchData();
    const dataInterval = setInterval(fetchData, 1000);
    const clockInterval = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      clearInterval(dataInterval);
      clearInterval(clockInterval);
    };
  }, [fetchConfig, fetchData, fetchHistoryDates, historyDate]);

  // Load historical snapshot when historyDate changes
  useEffect(() => {
    if (historyDate) {
      fetchHistoryData(historyDate);
    }
  }, [historyDate, fetchHistoryData]);

  const handleTabClick = (tab: ActiveTab) => {
    setActiveTab(tab);
    setTabOverridden(true);
  };

  const handleConfigUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret, base_url: baseUrl, data_feed: dataFeed }),
      });
      if (res.ok) {
        const result = await res.json();
        if (result.data_feed) setActiveFeed(result.data_feed);
        setFeedFellBack(false);
        setShowSettings(false);
        fetchData();
      }
    } catch {
      alert('Error updating configuration');
    }
  };

  const secondsAgo = lastScan > 0 ? Math.max(0, Math.floor(now - lastScan)) : null;

  function handleHistoryChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    if (val === '') {
      setHistoryDate(null);
      // resume live data immediately
      fetchData();
    } else {
      setHistoryDate(val);
    }
  }

  if (tradingSymbol) {
    return (
      <div className="container container--ticker-detail">
        <div className="main-col main-col--full">
          <AppHeader
            compact
            mode={mode}
            health={health}
            activeFeed={activeFeed}
            feedFellBack={feedFellBack}
            secondsAgo={null}
            historyDate={null}
            historyDates={[]}
            onHistoryChange={handleHistoryChange}
            onLookup={openTradingView}
            showSettings={false}
            onToggleSettings={() => {}}
            showScannerSource={false}
          />
          <main className="ticker-detail-main">
            <TickerDetailPage
              symbol={tradingSymbol}
              onBack={() => setTradingSymbol(null)}
              onSelectSymbol={openTradingView}
            />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      <div className="main-col">
      <AppHeader
        mode={mode}
        health={health}
        activeFeed={activeFeed}
        feedFellBack={feedFellBack}
        secondsAgo={secondsAgo}
        historyDate={historyDate}
        historyDates={historyDates}
        onHistoryChange={handleHistoryChange}
        onLookup={setSelectedSymbol}
        showSettings={showSettings}
        onToggleSettings={() => setShowSettings(s => !s)}
        showScannerSource={activeTab !== 'trading'}
      />

      {showSettings && (
        <div className="panel settings-panel">
          <h2 className="panel-title">Settings</h2>
          <form onSubmit={handleConfigUpdate}>
            <div className="form-group">
              <label>API Key ID</label>
              <input
                type="text"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="APCA_API_KEY_ID"
                required
              />
            </div>
            <div className="form-group">
              <label>API Secret Key</label>
              <input
                type="text"
                value={apiSecret}
                onChange={e => setApiSecret(e.target.value)}
                placeholder="••••••••••••••••"
                required
              />
            </div>
            <div className="form-group">
              <label>Base URL</label>
              <input
                type="url"
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Data Feed</label>
              <select
                value={dataFeed}
                onChange={e => setDataFeed(e.target.value)}
                className="feed-select"
              >
                {dataFeedOptions.map(f => (
                  <option key={f} value={f}>{DATA_FEED_LABELS[f] || f.toUpperCase()}</option>
                ))}
              </select>
              <span className="form-hint">
                IEX is free. SIP requires a paid Alpaca data subscription.
              </span>
            </div>
            <div className="form-row">
              <button type="submit">Update &amp; Connect</button>
              <button type="button" className="btn-secondary" onClick={() => setShowSettings(false)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <main className="panel">
        {/* ── Tab bar ───────────────────────────────────────────────── */}
        <TabNav
          activeTab={activeTab}
          onTabClick={handleTabClick}
          counts={{
            gappers: gappers.length,
            movers: movers.length,
            afterhours: afterhours.length,
            catalysts: catalysts.length,
            hodMomo: hodMomoStream.alerts.length,
            watchlist: watchlist.entries.length,
          }}
        />

        {historyDate && (
          <div className="history-banner">
            <span>Viewing {fmtHistoryDate(historyDate)}</span>
            <button
              className="history-banner-btn"
              onClick={() => { setHistoryDate(null); fetchData(); }}
            >
              Back to Live
            </button>
          </div>
        )}

        {/* ── Gappers tab ───────────────────────────────────────────── */}
        {activeTab === 'gappers' && (
          <>
            <div className="sub-tab-bar">
              <button
                className={`sub-tab ${gapperSubTab === 'all' ? 'active' : ''}`}
                onClick={() => setGapperSubTab('all')}
              >
                All Gaps
                {gappers.length > 0 && <span className="tab-count">{gappers.length}</span>}
              </button>
              <button
                className={`sub-tab ${gapperSubTab === 'small_cap' ? 'active' : ''}`}
                onClick={() => setGapperSubTab('small_cap')}
              >
                Small Cap
                {smallCapGappers.length > 0 && <span className="tab-count">{smallCapGappers.length}</span>}
              </button>
            </div>
            {(gapperSubTab === 'all' ? gappers : smallCapGappers).length > 0 ? (
              <ScannerTable
                columns={SCANNER_COLUMNS}
                data={gapperSubTab === 'all' ? sortedGappers : sortedSmallCapGappers}
                sortState={gapperSort}
                onSort={key => toggleSort(gapperSort, setGapperSort, key)}
                selectedSymbol={selectedSymbol}
                onSelect={setSelectedSymbol}
                onOpenTrading={openTradingView}
              />
            ) : (
              <EmptyState health={health} context={mode === 'market' ? 'premarket' : mode} />
            )}
          </>
        )}

        {/* ── News Catalysts tab (experimental) ────────────────────── */}
        {activeTab === 'catalysts' && (
          <>
            <div className="catalysts-description">
              News-first scanner — surfaces any ticker mentioned in recent market
              news regardless of exchange or size. Sorted by absolute gap magnitude.
            </div>
            {sortedCatalysts.length > 0 ? (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      {(
                        [
                          ['symbol', 'Symbol'],
                          ['previous_close', 'Prev Close'],
                          ['current_price', 'Price'],
                          ['gap_percent', 'Gap %'],
                          ['volume', 'Volume'],
                          ['catalyst_headline', 'Catalyst Headline'],
                          ['newest_headline_at', 'News Time'],
                        ] as [string, string][]
                      ).map(([key, label]) => (
                        <th
                          key={key}
                          className="sortable-th"
                          onClick={() => toggleSort(catalystSort, setCatalystSort, key)}
                          aria-sort={
                            catalystSort.key === key
                              ? catalystSort.dir === 'asc' ? 'ascending' : 'descending'
                              : 'none'
                          }
                        >
                          <span className="th-inner">
                            {label}
                            <span className={`sort-arrow${catalystSort.key === key ? ' active' : ''}`}>
                              {catalystSort.key === key
                                ? catalystSort.dir === 'asc' ? '↑' : '↓'
                                : '↕'}
                            </span>
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedCatalysts.map(c => (
                      <tr key={c.symbol} className={selectedSymbol === c.symbol ? 'row-selected' : ''}>
                        <td>
                          <SymbolSelectButton
                            symbol={c.symbol}
                            selected={selectedSymbol === c.symbol}
                            onSelect={setSelectedSymbol}
                            onOpenTrading={openTradingView}
                          />
                        </td>
                        <td>${c.previous_close.toFixed(2)}</td>
                        <td>${c.current_price.toFixed(2)}</td>
                        <td className={c.gap_percent >= 0 ? 'positive' : 'negative'}>
                          {fmtPct(c.gap_percent)}
                        </td>
                        <td>{fmtVolume(c.volume)}</td>
                        <td className="catalyst-headline-cell">
                          {c.catalyst_headline ? (
                            c.catalyst_url ? (
                              <a
                                href={c.catalyst_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="catalyst-headline-link"
                                title={c.catalyst_headline}
                              >
                                {c.catalyst_headline.length > 80
                                  ? `${c.catalyst_headline.slice(0, 80)}…`
                                  : c.catalyst_headline}
                              </a>
                            ) : (
                              <span title={c.catalyst_headline}>
                                {c.catalyst_headline.length > 80
                                  ? `${c.catalyst_headline.slice(0, 80)}…`
                                  : c.catalyst_headline}
                              </span>
                            )
                          ) : (
                            <span className="na-muted">—</span>
                          )}
                          {c.news_impact && (
                            <span
                              className="ni-catalyst-badge"
                              title={
                                (NEWS_IMPACT_CLASS_TOOLTIPS[c.news_impact.impact_class] ?? '') +
                                '\n\n' +
                                (c.news_impact.reasons?.slice(0, 4).join('\n') ?? '')
                              }
                            >
                              {NEWS_IMPACT_CLASS_LABELS[c.news_impact.impact_class] ??
                                c.news_impact.impact_class}
                              {' · '}
                              {(c.news_impact.confidence * 100).toFixed(0)}%
                            </span>
                          )}
                        </td>
                        <td><NewsCell newest_headline_at={c.newest_headline_at} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                {health.status === 'disconnected' || health.status === 'error'
                  ? (health.message || 'Check API keys in Settings.')
                  : 'No news catalysts found yet — scan running\u2026'}
              </div>
            )}
          </>
        )}

        {/* ── Movers tab ────────────────────────────────────────────── */}
        {activeTab === 'movers' && (
          <>
            {sortedMovers.length > 0 ? (
              <ScannerTable
                columns={SCANNER_COLUMNS}
                data={sortedMovers}
                sortState={moverSort}
                onSort={key => toggleSort(moverSort, setMoverSort, key)}
                selectedSymbol={selectedSymbol}
                onSelect={setSelectedSymbol}
                onOpenTrading={openTradingView}
              />
            ) : (
              <EmptyState health={health} context={mode === 'premarket' ? 'market' : mode} />
            )}
          </>
        )}

        {/* ── After Hours tab ───────────────────────────────────────── */}
        {activeTab === 'afterhours' && (
          <>
            {sortedAfterhours.length > 0 ? (
              <ScannerTable
                columns={SCANNER_COLUMNS}
                data={sortedAfterhours}
                sortState={afterhoursSort}
                onSort={key => toggleSort(afterhoursSort, setAfterhoursSort, key)}
                selectedSymbol={selectedSymbol}
                onSelect={setSelectedSymbol}
                onOpenTrading={openTradingView}
              />
            ) : (
              <EmptyState health={health} context={mode === 'market' ? 'afterhours' : mode} />
            )}
          </>
        )}

        {/* ── HOD Momo tab ──────────────────────────────────────────── */}
        {activeTab === 'hod_momo' && (
          <>
            {showHodSettings && (
              <HodMomoSettings
                config={hodMomoConfig}
                onClose={() => setShowHodSettings(false)}
              />
            )}
            <HodMomoTab
              alerts={hodMomoStream.alerts}
              connected={hodMomoStream.connected}
              config={hodMomoConfig}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              onOpenTrading={openTradingView}
              onOpenSettings={() => setShowHodSettings(s => !s)}
              dataFeed={activeFeed}
            />
          </>
        )}
        {activeTab === 'trading' && <TradingTab />}

        {/* ── Watchlist tab (Five Pillars) ──────────────────────────── */}
        {activeTab === 'strategy' && (
          <WatchlistTab
            entries={watchlist.entries}
            loading={watchlist.loading}
            error={watchlist.error}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={setSelectedSymbol}
            onOpenTrading={openTradingView}
          />
        )}

        {/* ── Reports (P&L calendar) ────────────────────────────────── */}
        {activeTab === 'reports' && <ReportsTab />}
      </main>
      </div>
      <SidePanel
        selectedSymbol={selectedSymbol}
        setSelectedSymbol={setSelectedSymbol}
        onOpenTrading={openTradingView}
      />
    </div>
  );
}

export default App;

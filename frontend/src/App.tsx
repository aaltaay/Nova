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
import { ScannerTable } from './components/ScannerTable';
import { CatalystsTable } from './components/CatalystsTable';
import { EmptyState } from './components/EmptyState';
import { SettingsPanel } from './components/SettingsPanel';
import type { Gapper, Mover, Afterhours, SortConfig } from './types/scanner';
import type { Catalyst } from './types/catalyst';
import { TradingTab } from './ibkr/TradingTab';
import { WatchlistTab } from './strategy/WatchlistTab';
import { useWatchlist } from './strategy/useWatchlist';
import { useWatchlistOverlay } from './strategy/useWatchlistOverlay';
import { ReportsTab } from './reports/ReportsTab';
import { TickerDetailPage } from './pages/TickerDetailPage';
import {
  SMALL_CAP_MIN, SMALL_CAP_MAX,
  SCANNER_COLUMNS,
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
  API_BASE_URL,
} from './constants';
import { isNovaApiDebug } from './debug';
import { scanAgeForTab } from './utils/scanAge';
import type { ScannerScanAges } from './utils/scanAge';

type Mode = MarketMode;
// ActiveTab is imported from components/TabNav — includes 'trading'
// SortDir / SortConfig now live in types/scanner (shared with ScannerTable)

interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
}

// Catalyst type now lives in types/catalyst.ts; Scanner formatters imported from
// utils/quoteFormat; ScannerTable + NewsCell live in components/ScannerTable
// EmptyState lives in components/EmptyState.tsx

// ── Constants ─────────────────────────────────────────────────────────────────

const API_URL = `${API_BASE_URL}/api`;

// ── Main App ──────────────────────────────────────────────────────────────────

function App() {
  const [mode, setMode] = useState<Mode>('loading');
  const [health, setHealth] = useState<HealthStatus>({ status: 'loading', latency_ms: 0 });
  const [gappers, setGappers] = useState<Gapper[]>([]);
  const [movers, setMovers] = useState<Mover[]>([]);
  const [afterhours, setAfterhours] = useState<Afterhours[]>([]);
  const [scanAges, setScanAges] = useState<ScannerScanAges>({
    gappers: 0,
    movers: 0,
    afterhours: 0,
  });
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
  const [discoveryProvider, setDiscoveryProvider] = useState(DISCOVERY_PROVIDER_DEFAULT);
  const [discoveryProviderOptions, setDiscoveryProviderOptions] = useState<string[]>(['alpaca', 'ibkr']);

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

  // Joins the polled Watchlist entries onto each scanner row by symbol (Five Pillars
  // + composite score) before sorting, so the new "Watch" column sorts correctly.
  const gappersWithWatchlist = useWatchlistOverlay(gappers, watchlist.entries);
  const moversWithWatchlist = useWatchlistOverlay(movers, watchlist.entries);
  const afterhoursWithWatchlist = useWatchlistOverlay(afterhours, watchlist.entries);

  const sortedGappers = useMemo(
    () => sortedArray(gappersWithWatchlist, gapperSort),
    [gappersWithWatchlist, gapperSort],
  );

  const smallCapGappers = useMemo(
    () => gappersWithWatchlist.filter(g =>
      g.market_cap != null &&
      g.market_cap >= SMALL_CAP_MIN &&
      g.market_cap < SMALL_CAP_MAX
    ),
    [gappersWithWatchlist],
  );

  const sortedSmallCapGappers = useMemo(
    () => sortedArray(smallCapGappers, gapperSort),
    [smallCapGappers, gapperSort],
  );

  const sortedMovers = useMemo(
    () => sortedArray(moversWithWatchlist, moverSort),
    [moversWithWatchlist, moverSort],
  );

  const sortedAfterhours = useMemo(
    () => sortedArray(afterhoursWithWatchlist, afterhoursSort),
    [afterhoursWithWatchlist, afterhoursSort],
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
        if (data.discovery_provider) setDiscoveryProvider(data.discovery_provider);
        if (Array.isArray(data.discovery_provider_options)) setDiscoveryProviderOptions(data.discovery_provider_options);
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

      let nextAges: Partial<ScannerScanAges> = {};

      if (gr.ok) {
        const data = await gr.json();
        if (data.health) {
          setHealth(data.health);
          if (data.health.feed_fell_back != null) setFeedFellBack(data.health.feed_fell_back);
        }
        if (data.mode) setMode(data.mode as Mode);
        if (data.data_feed) setActiveFeed(data.data_feed);
        if (Array.isArray(data.gappers)) setGappers(data.gappers);
        if (data.last_scan) nextAges = { ...nextAges, gappers: data.last_scan };
      }

      if (moversRes.ok) {
        const data = await moversRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, movers: data.last_scan };
        const gainers: Mover[] = Array.isArray(data.gainers) ? data.gainers : [];
        const losers: Mover[] = Array.isArray(data.losers) ? data.losers : [];
        setMovers([...gainers, ...losers]);
      }

      if (ahRes.ok) {
        const data = await ahRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, afterhours: data.last_scan };
        if (Array.isArray(data.afterhours)) setAfterhours(data.afterhours);
      }

      if (Object.keys(nextAges).length > 0) {
        setScanAges(prev => ({ ...prev, ...nextAges }));
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
        body: JSON.stringify({
          api_key: apiKey,
          api_secret: apiSecret,
          base_url: baseUrl,
          data_feed: dataFeed,
          discovery_provider: discoveryProvider,
        }),
      });
      if (res.ok) {
        const result = await res.json();
        if (result.data_feed) setActiveFeed(result.data_feed);
        if (result.discovery_provider) setDiscoveryProvider(result.discovery_provider);
        setFeedFellBack(false);
        setShowSettings(false);
        fetchData();
      }
    } catch {
      alert('Error updating configuration');
    }
  };

  const lastScan = scanAgeForTab(activeTab, scanAges);
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
        discoveryProvider={discoveryProvider}
      />

      {showSettings && (
        <SettingsPanel
          apiKey={apiKey}
          onApiKeyChange={setApiKey}
          apiSecret={apiSecret}
          onApiSecretChange={setApiSecret}
          baseUrl={baseUrl}
          onBaseUrlChange={setBaseUrl}
          dataFeed={dataFeed}
          onDataFeedChange={setDataFeed}
          dataFeedOptions={dataFeedOptions}
          discoveryProvider={discoveryProvider}
          onDiscoveryProviderChange={setDiscoveryProvider}
          discoveryProviderOptions={discoveryProviderOptions}
          onSubmit={handleConfigUpdate}
          onCancel={() => setShowSettings(false)}
        />
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
          <CatalystsTable
            catalysts={sortedCatalysts}
            sortState={catalystSort}
            onSort={key => toggleSort(catalystSort, setCatalystSort, key)}
            selectedSymbol={selectedSymbol}
            onSelect={setSelectedSymbol}
            onOpenTrading={openTradingView}
            health={health}
          />
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
        watchlistEntries={watchlist.entries}
        discoveryProvider={discoveryProvider}
        alpacaFeed={activeFeed}
      />
    </div>
  );
}

export default App;

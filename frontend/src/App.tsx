import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import {
  SMALL_CAP_MIN, SMALL_CAP_MAX,
  NEWS_FLAME_HOT_HOURS, NEWS_FLAME_WARM_HOURS, NEWS_FLAME_MAX_HOURS,
  REL_VOLUME_HIGH,
  GAPPER_MIN_GAP_PCT,
  CATALYSTS_EXPERIMENTAL_LABEL,
} from './constants';

type Mode = 'premarket' | 'market' | 'closed' | 'loading';
type SortDir = 'asc' | 'desc' | null;
interface SortConfig { key: string; dir: SortDir; }

interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
}

interface Gapper {
  symbol: string;
  previous_close: number;
  current_price: number;
  gap_percent: number;
  volume: number;
  rel_volume: number | null;
  has_news: boolean;
  newest_headline_at: string | null;
  market_cap: number | null;
  float: number | null;
  short_interest: number | null;
  short_ratio: number | null;
}

interface Gainer {
  symbol: string;
  price: number;
  change_pct: number;
  change_abs: number;
  volume: number;
  gap_percent: number | null;
  rel_volume: number | null;
  has_news: boolean;
  newest_headline_at: string | null;
  market_cap: number | null;
  float: number | null;
  short_interest: number | null;
  short_ratio: number | null;
}

// Movers (top gainers + top losers from screener) share the same shape as Gainer
type Mover = Gainer;

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
}

// ── Ticker Detail Types ────────────────────────────────────────────────────────

interface BarData {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  trade_count: number | null;
  vwap: number | null;
  timestamp: string | null;
}

interface TradeData {
  price: number | null;
  size: number | null;
  exchange: string | null;
  timestamp: string | null;
}

interface QuoteData {
  bid_price: number | null;
  bid_size: number | null;
  ask_price: number | null;
  ask_size: number | null;
  timestamp: string | null;
}

interface SnapshotData {
  latest_trade: TradeData | null;
  latest_quote: QuoteData | null;
  minute_bar: BarData | null;
  daily_bar: BarData | null;
  prev_daily_bar: BarData | null;
}

interface AssetInfo {
  name: string;
  exchange: string;
  asset_class: string;
  tradable: boolean;
  marginable: boolean;
  shortable: boolean;
  easy_to_borrow: boolean;
  fractionable: boolean;
  maintenance_margin_requirement: number | null;
}

interface NewsArticle {
  headline: string;
  summary: string;
  author: string;
  source: string;
  url: string;
  created_at: string;
  symbols: string[];
  images: { url: string; size: string }[];
}

interface FundamentalsData {
  market_cap: number | null;
  shares_outstanding: number | null;
  float_shares: number | null;
  short_interest: number | null;
  short_ratio: number | null;
  short_percent_of_float: number | null;
  pe_ratio: number | null;
  forward_pe: number | null;
  eps: number | null;
  sector: string | null;
  industry: string | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  dividend_yield: number | null;
  beta: number | null;
  earnings_date: string | null;
  recent_split: string | null;
}

interface TickerTradeUpdate {
  type: 'trade_update';
  price: number;
  size: number | null;
  timestamp: string | null;
}

interface TickerDetail {
  symbol: string;
  asset: AssetInfo;
  snapshot: SnapshotData;
  avg_volume: number | null;
  rel_volume: number | null;
  news: NewsArticle[];
  fundamentals: FundamentalsData | null;
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtVolume(v: number | null | undefined): string {
  if (!v) return '—';
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

function fmtMarketCap(v: number | null | undefined): string {
  if (v == null) return '—';
  if (v >= 1_000_000_000_000) return `$${(v / 1_000_000_000_000).toFixed(2)}T`;
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v}`;
}

function fmtPct(frac: number | null, fallback = 'N/A'): string {
  if (frac == null) return fallback;
  return `${frac > 0 ? '+' : ''}${(frac * 100).toFixed(2)}%`;
}

function fmtPrice(p: number | null | undefined): string {
  if (p == null) return '—';
  return `$${p.toFixed(2)}`;
}


function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── Small UI Helpers ──────────────────────────────────────────────────────────

function NewsCell({ newest_headline_at }: { newest_headline_at: string | null }) {
  if (!newest_headline_at) return <span className="na-muted">—</span>;
  const ageHours = (Date.now() - new Date(newest_headline_at).getTime()) / 3_600_000;
  if (ageHours > NEWS_FLAME_MAX_HOURS) return <span className="na-muted">—</span>;
  let colorClass: string;
  if (ageHours <= NEWS_FLAME_HOT_HOURS) colorClass = 'flame-hot';
  else if (ageHours <= NEWS_FLAME_WARM_HOURS) colorClass = 'flame-warm';
  else colorClass = 'flame-cool';
  const label = ageHours < 1 ? `${Math.round(ageHours * 60)}m ago` : `${Math.floor(ageHours)}h ago`;
  return <span className={`news-flame ${colorClass}`} title={label}>🔥</span>;
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
  return <div className="empty-state">No gainers in the feed right now.</div>;
}

// ── useTickerStream hook ──────────────────────────────────────────────────────

function useTickerStream(symbol: string | null): { detail: TickerDetail | null; loading: boolean } {
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!symbol) {
      setDetail(null);
      setLoading(false);
      return;
    }

    setDetail(null);
    setLoading(true);

    const ws = new WebSocket(`${WS_URL}/ticker/${symbol}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'initial') {
          const { type: _t, ...data } = msg;
          setDetail(data as TickerDetail);
          setLoading(false);
        } else if (msg.type === 'trade_update') {
          const update = msg as TickerTradeUpdate;
          setDetail(prev => {
            if (!prev) return prev;
            const prevClose = prev.snapshot?.prev_daily_bar?.close ?? null;
            const newPrice = update.price;
            // Rebuild snapshot with updated trade price
            const newSnapshot = {
              ...prev.snapshot,
              latest_trade: {
                price: newPrice,
                size: update.size ?? prev.snapshot?.latest_trade?.size ?? null,
                timestamp: update.timestamp ?? prev.snapshot?.latest_trade?.timestamp ?? null,
                exchange: prev.snapshot?.latest_trade?.exchange ?? null,
              },
            };
            // Recompute rel_volume if avg is known
            const dailyVol = prev.snapshot?.daily_bar?.volume ?? null;
            const avgVol = prev.avg_volume;
            const relVol = dailyVol != null && avgVol != null && avgVol > 0
              ? Math.round((dailyVol / avgVol) * 100) / 100
              : prev.rel_volume;
            void prevClose; // prevClose used implicitly via derived values in render
            return { ...prev, snapshot: newSnapshot, rel_volume: relVol };
          });
        }
        // ignore 'ping' messages
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => setLoading(false);
    ws.onclose = () => {
      if (wsRef.current === ws) setLoading(false);
    };

    return () => {
      wsRef.current = null;
      ws.close();
    };
  }, [symbol]);

  return { detail, loading };
}

// ── Compact Ticker Detail ─────────────────────────────────────────────────────

function fmtTimestamp(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return iso;
  }
}

function CompactGridCell({ label, value, valueClass }: { label: string; value: React.ReactNode; valueClass?: string }) {
  return (
    <div className="cq-cell">
      <span className="cq-label">{label}</span>
      <span className={`cq-value${valueClass ? ' ' + valueClass : ''}`}>{value}</span>
    </div>
  );
}

function TickerDetailContent({
  detail,
}: {
  detail: TickerDetail;
}) {
  const [newsExpanded, setNewsExpanded] = useState(false);
  const snap = detail.snapshot;
  const asset = detail.asset;
  const trade = snap?.latest_trade;
  const daily = snap?.daily_bar;
  const prevDaily = snap?.prev_daily_bar;

  const price = trade?.price ?? daily?.close ?? null;
  const prevClose = prevDaily?.close ?? null;
  const changeAbs = (price != null && prevClose != null) ? price - prevClose : null;
  const changePct = (changeAbs != null && prevClose) ? changeAbs / prevClose : null;
  const isPositive = (changePct ?? 0) >= 0;

  const lastUpdated = trade?.timestamp ?? snap?.latest_quote?.timestamp ?? null;

  // Pipe-delimited description: Name | Country | Exchange | Sector | Industry
  const descParts: string[] = [];
  if (asset?.name) descParts.push(asset.name);
  if (asset?.exchange) descParts.push(asset.exchange);
  if (detail.fundamentals?.sector) descParts.push(detail.fundamentals.sector);
  if (detail.fundamentals?.industry) descParts.push(detail.fundamentals.industry);

  const NEWS_DEFAULT = 3;
  const visibleNews = newsExpanded ? detail.news : detail.news.slice(0, NEWS_DEFAULT);

  // Gap % from prev close to today's open (or current price if no open)
  const todayOpen = daily?.open ?? null;
  const gapPct = (todayOpen != null && prevClose != null && prevClose !== 0)
    ? (todayOpen - prevClose) / prevClose
    : null;

  return (
    <div className="cq-root">
      {/* Header row */}
      <div className="cq-header">
        <div className="cq-symbol-row">
          <span className="cq-symbol">{detail.symbol}</span>
          {changeAbs != null && (
            <span className="cq-trend">{isPositive ? '▲' : '▼'}</span>
          )}
        </div>
        {price != null && (
          <div className="cq-price-row">
            <span className="cq-price">{price.toFixed(2)}</span>
            {changeAbs != null && (
              <span className={`cq-change ${isPositive ? 'positive' : 'negative'}`}>
                {changeAbs >= 0 ? '+' : ''}{changeAbs.toFixed(2)} ({fmtPct(changePct)})
              </span>
            )}
          </div>
        )}
      </div>

      {/* Description */}
      {descParts.length > 0 && (
        <div className="cq-description">{descParts.join(' | ')}</div>
      )}

      {/* Last updated */}
      {lastUpdated && (
        <div className="cq-timestamp">Last updated on {fmtTimestamp(lastUpdated)}</div>
      )}

      {/* News section */}
      {detail.news.length > 0 && (
        <div className="cq-news-section">
          <div className="cq-news-header">
            <span className="cq-news-title">News Headline</span>
            {detail.news.length > NEWS_DEFAULT && (
              <button className="cq-news-more" onClick={() => setNewsExpanded(x => !x)}>
                {newsExpanded ? 'Less ▲' : `More ▼`}
              </button>
            )}
          </div>
          <div className="cq-news-list">
            {visibleNews.map((article, i) => {
              const ageHours = (Date.now() - new Date(article.created_at).getTime()) / 3_600_000;
              const hasFlame = ageHours <= NEWS_FLAME_MAX_HOURS;
              const flameClass = ageHours <= NEWS_FLAME_HOT_HOURS ? 'flame-hot'
                : ageHours <= NEWS_FLAME_WARM_HOURS ? 'flame-warm' : 'flame-cool';
              return (
                <div key={i} className="cq-news-item">
                  <span className={`cq-news-icon ${hasFlame ? `news-flame ${flameClass}` : 'cq-news-icon-blank'}`}>
                    {hasFlame ? '🔥' : ''}
                  </span>
                  <a
                    className="cq-news-link"
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {article.headline}
                  </a>
                  <span className="cq-news-time">{timeAgo(article.created_at)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Data grid */}
      <div className="cq-grid">
        <CompactGridCell label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
        <CompactGridCell label="Volume" value={fmtVolume(daily?.volume)} />

        <CompactGridCell
          label="Relative Volume (Daily)"
          value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
          valueClass={detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined}
        />
        <CompactGridCell label="Relative Volume (5 min %)" value="—" />

        <CompactGridCell
          label="Gap(%)"
          value={gapPct != null ? `${(gapPct * 100).toFixed(2)}` : '—'}
          valueClass={gapPct != null ? (gapPct >= 0 ? 'positive' : 'negative') : undefined}
        />
        <CompactGridCell label="Volume In 5 Minutes" value="—" />

        <CompactGridCell label="Previous Close" value={fmtPrice(prevClose)} />
        <CompactGridCell label="High Price" value={fmtPrice(daily?.high)} />

        <CompactGridCell label="Low Price" value={fmtPrice(daily?.low)} />
        <CompactGridCell label="High In 52 Weeks" value={fmtPrice(detail.fundamentals?.fifty_two_week_high)} />

        <CompactGridCell label="Low In 52 Weeks" value={fmtPrice(detail.fundamentals?.fifty_two_week_low)} />
        <CompactGridCell label="Short Interest" value={fmtVolume(detail.fundamentals?.short_interest)} />

        <CompactGridCell
          label="Earnings Date"
          value={detail.fundamentals?.earnings_date ?? '—'}
        />
        <CompactGridCell label="Market Cap" value={fmtMarketCap(detail.fundamentals?.market_cap)} />

        <CompactGridCell label="Industry" value={detail.fundamentals?.industry ?? '—'} />
        <CompactGridCell label="Sector" value={detail.fundamentals?.sector ?? '—'} />

        <CompactGridCell
          label="Recent Split"
          value={detail.fundamentals?.recent_split ?? '—'}
        />
        <CompactGridCell label="Exchange Group" value={asset?.exchange ?? '—'} />
      </div>

      {/* Bottom timestamp */}
      {lastUpdated && (
        <div className="cq-timestamp cq-timestamp-bottom">Last updated on {fmtTimestamp(lastUpdated)}</div>
      )}
    </div>
  );
}

// ── Persistent Side Panel ─────────────────────────────────────────────────────

function SidePanel({
  selectedSymbol,
  setSelectedSymbol,
}: {
  selectedSymbol: string | null;
  setSelectedSymbol: (sym: string | null) => void;
}) {
  const [input, setInput] = useState(selectedSymbol ?? '');
  const { detail, loading } = useTickerStream(selectedSymbol);

  useEffect(() => {
    setInput(selectedSymbol ?? '');
  }, [selectedSymbol]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    setSelectedSymbol(sym || null);
  }

  return (
    <aside className="side-panel">
      <div className="side-panel-search">
        <form className="side-search-form" onSubmit={handleSubmit}>
          <input
            className="side-search-input"
            type="text"
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            placeholder="Symbol, e.g. AAPL"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" className="side-search-btn">Look Up</button>
        </form>
      </div>
      <div className="side-panel-body">
        {loading && (
          <div className="detail-loading">
            <div className="detail-loading-spinner" />
            <span>Loading…</span>
          </div>
        )}
        {!loading && detail && (
          <div className="detail-body">
            <TickerDetailContent detail={detail} />
          </div>
        )}
        {!loading && !detail && selectedSymbol && (
          <div className="detail-empty">No data found for {selectedSymbol}.</div>
        )}
        {!loading && !selectedSymbol && (
          <div className="detail-empty">Enter a ticker symbol above to look up a stock quote.</div>
        )}
      </div>
    </aside>
  );
}

// ── Constants ─────────────────────────────────────────────────────────────────

const MODE_LABELS: Record<Mode, string> = {
  loading: 'Connecting…',
  premarket: 'Pre-Market',
  market: 'Market Hours',
  closed: 'Market Closed',
};

const API_URL = 'http://localhost:8000/api';
const WS_URL = 'ws://localhost:8000/ws';

// ── Main App ──────────────────────────────────────────────────────────────────

function App() {
  const [mode, setMode] = useState<Mode>('loading');
  const [health, setHealth] = useState<HealthStatus>({ status: 'loading', latency_ms: 0 });
  const [gappers, setGappers] = useState<Gapper[]>([]);
  const [gainers, setGainers] = useState<Gainer[]>([]);
  const [lastScan, setLastScan] = useState<number>(0);
  const [showSettings, setShowSettings] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [activeTab, setActiveTab] = useState<'gappers' | 'gainers' | 'movers' | 'catalysts'>('gappers');
  const [tabOverridden, setTabOverridden] = useState(false);
  const [gapperSubTab, setGapperSubTab] = useState<'all' | 'small_cap'>('all');
  const [moversSubTab, setMoversSubTab] = useState<'gainers' | 'losers'>('gainers');
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [gainerSort, setGainerSort] = useState<SortConfig>({ key: '', dir: null });
  const [moverSort, setMoverSort] = useState<SortConfig>({ key: '', dir: null });
  const [catalystSort, setCatalystSort] = useState<SortConfig>({ key: '', dir: null });

  // Catalysts tab state
  const [catalysts, setCatalysts] = useState<Catalyst[]>([]);

  // Top Movers tab state
  const [moverGainers, setMoverGainers] = useState<Mover[]>([]);
  const [moverLosers, setMoverLosers] = useState<Mover[]>([]);

  // Ticker detail state (side panel)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  // Settings form state
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.alpaca.markets');

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

  const sortedGainers = useMemo(
    () => sortedArray(gainers, gainerSort),
    [gainers, gainerSort],
  );

  const sortedMoverGainers = useMemo(
    () => sortedArray(moverGainers, moverSort),
    [moverGainers, moverSort],
  );

  const sortedMoverLosers = useMemo(
    () => sortedArray(moverLosers, moverSort),
    [moverLosers, moverSort],
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
      }
    } catch {
      // silent
    }
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const [gr, gainRes, moversRes, catalystRes] = await Promise.all([
        fetch(`${API_URL}/gappers`),
        fetch(`${API_URL}/gainers`),
        fetch(`${API_URL}/movers`),
        fetch(`${API_URL}/news-catalysts`),
      ]);

      if (gr.ok) {
        const data = await gr.json();
        if (data.health) setHealth(data.health);
        if (data.mode) setMode(data.mode as Mode);
        if (Array.isArray(data.gappers)) setGappers(data.gappers);
        if (data.mode === 'premarket' && data.last_scan) setLastScan(data.last_scan);
      }

      if (gainRes.ok) {
        const data = await gainRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (Array.isArray(data.gainers)) setGainers(data.gainers);
        if (data.mode === 'market' && data.last_scan) setLastScan(data.last_scan);
      }

      if (moversRes.ok) {
        const data = await moversRes.json();
        if (Array.isArray(data.gainers)) setMoverGainers(data.gainers);
        if (Array.isArray(data.losers)) setMoverLosers(data.losers);
      }

      if (catalystRes.ok) {
        const data = await catalystRes.json();
        if (Array.isArray(data.catalysts)) setCatalysts(data.catalysts);
      }
    } catch {
      setHealth({ status: 'disconnected', latency_ms: 0, message: 'Backend unreachable' });
    }
  }, []);


  // Auto-switch tab when mode changes, unless user has manually picked a tab
  useEffect(() => {
    if (!tabOverridden) {
      setActiveTab(mode === 'market' ? 'gainers' : 'gappers');
    }
  }, [mode, tabOverridden]);

  useEffect(() => {
    fetchConfig();
    fetchData();
    const dataInterval = setInterval(fetchData, 1000);
    const clockInterval = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      clearInterval(dataInterval);
      clearInterval(clockInterval);
    };
  }, [fetchConfig, fetchData]);

  const handleTabClick = (tab: 'gappers' | 'gainers' | 'movers' | 'catalysts') => {
    setActiveTab(tab);
    setTabOverridden(true);
  };

  const handleConfigUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret, base_url: baseUrl }),
      });
      if (res.ok) {
        setShowSettings(false);
        fetchData();
      }
    } catch {
      alert('Error updating configuration');
    }
  };

  // lastScan is a Unix wall-clock timestamp (seconds) from the server
  const secondsAgo = lastScan > 0 ? Math.max(0, Math.floor(now - lastScan)) : null;

  return (
    <div className="container">
      <div className="main-col">
      <header>
        <div className="header-left">
          <h1>B.L.A.S.T.</h1>
          <span className={`mode-badge mode-${mode}`}>{MODE_LABELS[mode]}</span>
        </div>
        <div className="header-right">
          <div className="status-indicator">
            <span className={`dot ${dotClass(health.status)}`} />
            <span style={{ textTransform: 'capitalize' }}>{health.status}</span>
            {health.latency_ms > 0 && <span>({health.latency_ms}ms)</span>}
            {health.message && health.status !== 'connected' && (
              <span className="status-hint" title={health.message}>
                {' '}— {health.message.length > 80 ? `${health.message.slice(0, 80)}…` : health.message}
              </span>
            )}
          </div>
          <button
            className={`settings-btn ${showSettings ? 'active' : ''}`}
            onClick={() => setShowSettings(s => !s)}
          >
            Settings
          </button>
        </div>
      </header>

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
                type="password"
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
        <div className="tab-bar">
          <button
            className={`tab ${activeTab === 'gappers' ? 'active' : ''}`}
            onClick={() => handleTabClick('gappers')}
          >
            Gappers
            {gappers.length > 0 && <span className="tab-count">{gappers.length}</span>}
          </button>
          <button
            className={`tab ${activeTab === 'gainers' ? 'active' : ''}`}
            onClick={() => handleTabClick('gainers')}
          >
            Gainers
            {gainers.length > 0 && <span className="tab-count">{gainers.length}</span>}
          </button>
          <button
            className={`tab ${activeTab === 'movers' ? 'active' : ''}`}
            onClick={() => handleTabClick('movers')}
          >
            Top Movers
            {(moverGainers.length > 0 || moverLosers.length > 0) && (
              <span className="tab-count">{moverGainers.length + moverLosers.length}</span>
            )}
          </button>
          <button
            className={`tab ${activeTab === 'catalysts' ? 'active' : ''}`}
            onClick={() => handleTabClick('catalysts')}
          >
            Catalysts
            <span className="tab-badge-experimental">{CATALYSTS_EXPERIMENTAL_LABEL}</span>
            {catalysts.length > 0 && <span className="tab-count">{catalysts.length}</span>}
          </button>
          <div className="tab-spacer" />
          {secondsAgo != null && (
            <span className="scan-age">updated {secondsAgo}s ago</span>
          )}
        </div>

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
                          ['rel_volume', 'Rel. Volume'],
                          ['newest_headline_at', 'News'],
                          ['market_cap', 'Mkt Cap'],
                          ['float', 'Float'],
                          ['short_interest', 'Short Int.'],
                          ['short_ratio', 'Short Ratio'],
                        ] as [string, string][]
                      ).map(([key, label]) => (
                        <th
                          key={key}
                          className="sortable-th"
                          onClick={() => toggleSort(gapperSort, setGapperSort, key)}
                          aria-sort={
                            gapperSort.key === key
                              ? gapperSort.dir === 'asc' ? 'ascending' : 'descending'
                              : 'none'
                          }
                        >
                          <span className="th-inner">
                            {label}
                            <span className={`sort-arrow${gapperSort.key === key ? ' active' : ''}`}>
                              {gapperSort.key === key
                                ? gapperSort.dir === 'asc' ? '↑' : '↓'
                                : '↕'}
                            </span>
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(gapperSubTab === 'all' ? sortedGappers : sortedSmallCapGappers).map(g => (
                      <tr key={g.symbol} className={selectedSymbol === g.symbol ? 'row-selected' : ''}>
                        <td>
                          <button
                            className={`symbol-btn${selectedSymbol === g.symbol ? ' active' : ''}`}
                            onClick={() => setSelectedSymbol(g.symbol)}
                          >
                            {g.symbol}
                          </button>
                        </td>
                        <td>${g.previous_close.toFixed(2)}</td>
                        <td>${g.current_price.toFixed(2)}</td>
                        <td className={g.gap_percent >= 0 ? 'positive' : 'negative'}>
                          {fmtPct(g.gap_percent)}
                        </td>
                        <td>{fmtVolume(g.volume)}</td>
                        <td>{g.rel_volume != null ? `${g.rel_volume}x` : <span className="na-muted">N/A</span>}</td>
                        <td><NewsCell newest_headline_at={g.newest_headline_at} /></td>
                        <td>{g.market_cap != null ? fmtMarketCap(g.market_cap) : <span className="na-muted">—</span>}</td>
                        <td>{g.float != null ? fmtVolume(g.float) : <span className="na-muted">—</span>}</td>
                        <td>{g.short_interest != null ? fmtVolume(g.short_interest) : <span className="na-muted">—</span>}</td>
                        <td>{g.short_ratio != null ? g.short_ratio.toFixed(1) : <span className="na-muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
                          <button
                            className={`symbol-btn${selectedSymbol === c.symbol ? ' active' : ''}`}
                            onClick={() => setSelectedSymbol(c.symbol)}
                          >
                            {c.symbol}
                          </button>
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

        {/* ── Top Movers tab ────────────────────────────────────────── */}
        {activeTab === 'movers' && (
          <>
            <div className="sub-tab-bar">
              <button
                className={`sub-tab ${moversSubTab === 'gainers' ? 'active' : ''}`}
                onClick={() => setMoversSubTab('gainers')}
              >
                Top Gainers
                {moverGainers.length > 0 && <span className="tab-count">{moverGainers.length}</span>}
              </button>
              <button
                className={`sub-tab ${moversSubTab === 'losers' ? 'active' : ''}`}
                onClick={() => setMoversSubTab('losers')}
              >
                Top Losers
                {moverLosers.length > 0 && <span className="tab-count">{moverLosers.length}</span>}
              </button>
            </div>
            {(moversSubTab === 'gainers' ? moverGainers : moverLosers).length > 0 ? (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      {(
                        [
                          ['symbol', 'Symbol'],
                          ['price', 'Price'],
                          ['change_pct', 'Change %'],
                          ['change_abs', 'Change $'],
                          ['volume', 'Volume'],
                          ['rel_volume', 'Rel. Volume'],
                          ['newest_headline_at', 'News'],
                          ['market_cap', 'Mkt Cap'],
                          ['float', 'Float'],
                          ['short_interest', 'Short Int.'],
                          ['short_ratio', 'Short Ratio'],
                        ] as [string, string][]
                      ).map(([key, label]) => (
                        <th
                          key={key}
                          className="sortable-th"
                          onClick={() => toggleSort(moverSort, setMoverSort, key)}
                          aria-sort={
                            moverSort.key === key
                              ? moverSort.dir === 'asc' ? 'ascending' : 'descending'
                              : 'none'
                          }
                        >
                          <span className="th-inner">
                            {label}
                            <span className={`sort-arrow${moverSort.key === key ? ' active' : ''}`}>
                              {moverSort.key === key
                                ? moverSort.dir === 'asc' ? '↑' : '↓'
                                : '↕'}
                            </span>
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(moversSubTab === 'gainers' ? sortedMoverGainers : sortedMoverLosers).map(m => (
                      <tr key={m.symbol} className={selectedSymbol === m.symbol ? 'row-selected' : ''}>
                        <td>
                          <button
                            className={`symbol-btn${selectedSymbol === m.symbol ? ' active' : ''}`}
                            onClick={() => setSelectedSymbol(m.symbol)}
                          >
                            {m.symbol}
                          </button>
                        </td>
                        <td>${m.price.toFixed(2)}</td>
                        <td className={m.change_pct >= 0 ? 'positive' : 'negative'}>
                          {fmtPct(m.change_pct)}
                        </td>
                        <td className={m.change_abs >= 0 ? 'positive' : 'negative'}>
                          {m.change_abs >= 0 ? '+' : ''}{m.change_abs.toFixed(2)}
                        </td>
                        <td>{fmtVolume(m.volume)}</td>
                        <td>{m.rel_volume != null ? `${m.rel_volume}x` : <span className="na-muted">N/A</span>}</td>
                        <td><NewsCell newest_headline_at={m.newest_headline_at} /></td>
                        <td>{m.market_cap != null ? fmtMarketCap(m.market_cap) : <span className="na-muted">—</span>}</td>
                        <td>{m.float != null ? fmtVolume(m.float) : <span className="na-muted">—</span>}</td>
                        <td>{m.short_interest != null ? fmtVolume(m.short_interest) : <span className="na-muted">—</span>}</td>
                        <td>{m.short_ratio != null ? m.short_ratio.toFixed(1) : <span className="na-muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                {health.status === 'disconnected' || health.status === 'error'
                  ? (health.message || 'Check API keys in Settings.')
                  : mode === 'loading'
                    ? 'Loading market data…'
                    : 'Fetching previous session\'s movers — loading…'}
              </div>
            )}
          </>
        )}

        {/* ── Gainers tab ───────────────────────────────────────────── */}
        {activeTab === 'gainers' && (
          <>
            {gainers.length > 0 ? (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      {(
                        [
                          ['symbol', 'Symbol'],
                          ['price', 'Price'],
                          ['change_pct', 'Change %'],
                          ['gap_percent', 'Gap %'],
                          ['volume', 'Volume'],
                          ['rel_volume', 'Rel. Volume'],
                          ['newest_headline_at', 'News'],
                          ['market_cap', 'Mkt Cap'],
                          ['float', 'Float'],
                          ['short_interest', 'Short Int.'],
                          ['short_ratio', 'Short Ratio'],
                        ] as [string, string][]
                      ).map(([key, label]) => (
                        <th
                          key={key}
                          className="sortable-th"
                          onClick={() => toggleSort(gainerSort, setGainerSort, key)}
                          aria-sort={
                            gainerSort.key === key
                              ? gainerSort.dir === 'asc' ? 'ascending' : 'descending'
                              : 'none'
                          }
                        >
                          <span className="th-inner">
                            {label}
                            <span className={`sort-arrow${gainerSort.key === key ? ' active' : ''}`}>
                              {gainerSort.key === key
                                ? gainerSort.dir === 'asc' ? '↑' : '↓'
                                : '↕'}
                            </span>
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedGainers.map(g => (
                      <tr key={g.symbol} className={selectedSymbol === g.symbol ? 'row-selected' : ''}>
                        <td>
                          <button
                            className={`symbol-btn${selectedSymbol === g.symbol ? ' active' : ''}`}
                            onClick={() => setSelectedSymbol(g.symbol)}
                          >
                            {g.symbol}
                          </button>
                        </td>
                        <td>${g.price.toFixed(2)}</td>
                        <td className={g.change_pct >= 0 ? 'positive' : 'negative'}>
                          {fmtPct(g.change_pct)}
                        </td>
                        <td className={g.gap_percent != null && g.gap_percent >= 0 ? 'positive' : g.gap_percent != null ? 'negative' : ''}>
                          {fmtPct(g.gap_percent)}
                        </td>
                        <td>{fmtVolume(g.volume)}</td>
                        <td>{g.rel_volume != null ? `${g.rel_volume}x` : <span className="na-muted">N/A</span>}</td>
                        <td><NewsCell newest_headline_at={g.newest_headline_at} /></td>
                        <td>{g.market_cap != null ? fmtMarketCap(g.market_cap) : <span className="na-muted">—</span>}</td>
                        <td>{g.float != null ? fmtVolume(g.float) : <span className="na-muted">—</span>}</td>
                        <td>{g.short_interest != null ? fmtVolume(g.short_interest) : <span className="na-muted">—</span>}</td>
                        <td>{g.short_ratio != null ? g.short_ratio.toFixed(1) : <span className="na-muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState health={health} context={mode === 'premarket' ? 'market' : mode} />
            )}
          </>
        )}
      </main>
      </div>
      <SidePanel selectedSymbol={selectedSymbol} setSelectedSymbol={setSelectedSymbol} />
    </div>
  );
}

function dotClass(status: string): string {
  if (status === 'connected') return 'connected';
  if (status === 'loading') return 'loading';
  return 'disconnected';
}

export default App;

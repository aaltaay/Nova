import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import {
  SMALL_CAP_MIN, SMALL_CAP_MAX,
  NEWS_FLAME_HOT_HOURS, NEWS_FLAME_WARM_HOURS, NEWS_FLAME_MAX_HOURS,
  REL_VOLUME_HIGH,
  GAPPER_MIN_GAP_PCT,
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

function fmtNum(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—';
  return n.toFixed(decimals);
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

// ── Ticker Detail Panel ───────────────────────────────────────────────────────

function DetailRow({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className={`detail-value${className ? ' ' + className : ''}`}>{value}</span>
    </div>
  );
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="detail-section">
      <div className="detail-section-title">{title}</div>
      {children}
    </div>
  );
}

function BoolBadge({ value, trueLabel = 'Yes', falseLabel = 'No' }: { value: boolean; trueLabel?: string; falseLabel?: string }) {
  return (
    <span className={`bool-badge ${value ? 'bool-yes' : 'bool-no'}`}>
      {value ? trueLabel : falseLabel}
    </span>
  );
}

function TickerDetailPanel({
  detail,
  loading,
  onClose,
}: {
  detail: TickerDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const snap = detail?.snapshot;
  const asset = detail?.asset;
  const trade = snap?.latest_trade;
  const quote = snap?.latest_quote;
  const daily = snap?.daily_bar;
  const prevDaily = snap?.prev_daily_bar;
  const minuteBar = snap?.minute_bar;

  const price = trade?.price ?? daily?.close ?? null;
  const prevClose = prevDaily?.close ?? null;
  const changeAbs = (price != null && prevClose != null) ? price - prevClose : null;
  const changePct = (changeAbs != null && prevClose) ? changeAbs / prevClose : null;
  const isPositive = (changePct ?? 0) >= 0;

  return (
    <>
      <div className="detail-overlay" onClick={onClose} />
      <div className="detail-panel" ref={panelRef} role="dialog" aria-modal="true">
        {loading || !detail ? (
          <div className="detail-loading">
            <div className="detail-loading-spinner" />
            <span>Loading…</span>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="detail-header">
              <div className="detail-header-left">
                <span className="detail-symbol">{detail.symbol}</span>
                {asset?.exchange && (
                  <span className="detail-exchange-badge">{asset.exchange}</span>
                )}
                {asset?.name && (
                  <span className="detail-company-name">{asset.name}</span>
                )}
              </div>
              <button className="detail-close" onClick={onClose} aria-label="Close">✕</button>
            </div>

            <div className="detail-body">
              {/* Price Overview */}
              <DetailSection title="Price">
                <DetailRow label="Last Trade" value={fmtPrice(price)} />
                {changeAbs != null && (
                  <DetailRow
                    label="Change"
                    value={`${changeAbs >= 0 ? '+' : ''}${fmtNum(changeAbs)} (${fmtPct(changePct)})`}
                    className={isPositive ? 'positive' : 'negative'}
                  />
                )}
                {quote && (
                  <>
                    <DetailRow
                      label="Bid"
                      value={`${fmtPrice(quote.bid_price)} × ${quote.bid_size ?? '—'}`}
                    />
                    <DetailRow
                      label="Ask"
                      value={`${fmtPrice(quote.ask_price)} × ${quote.ask_size ?? '—'}`}
                    />
                    {quote.bid_price != null && quote.ask_price != null && (
                      <DetailRow
                        label="Spread"
                        value={`$${(quote.ask_price - quote.bid_price).toFixed(3)}`}
                      />
                    )}
                  </>
                )}
              </DetailSection>

              {/* Daily Bar */}
              {daily && (
                <DetailSection title="Today's Bar">
                  <DetailRow label="Open" value={fmtPrice(daily.open)} />
                  <DetailRow label="High" value={fmtPrice(daily.high)} />
                  <DetailRow label="Low" value={fmtPrice(daily.low)} />
                  <DetailRow label="Close" value={fmtPrice(daily.close)} />
                  <DetailRow label="VWAP" value={fmtPrice(daily.vwap)} />
                  <DetailRow label="Trades" value={daily.trade_count?.toLocaleString() ?? '—'} />
                </DetailSection>
              )}

              {/* Previous Daily Bar */}
              {prevDaily && (
                <DetailSection title="Previous Day">
                  <DetailRow label="Open" value={fmtPrice(prevDaily.open)} />
                  <DetailRow label="High" value={fmtPrice(prevDaily.high)} />
                  <DetailRow label="Low" value={fmtPrice(prevDaily.low)} />
                  <DetailRow label="Close" value={fmtPrice(prevDaily.close)} />
                  <DetailRow label="VWAP" value={fmtPrice(prevDaily.vwap)} />
                  <DetailRow label="Trades" value={prevDaily.trade_count?.toLocaleString() ?? '—'} />
                </DetailSection>
              )}

              {/* Minute Bar */}
              {minuteBar && (
                <DetailSection title="Last Minute Bar">
                  <DetailRow label="Open" value={fmtPrice(minuteBar.open)} />
                  <DetailRow label="High" value={fmtPrice(minuteBar.high)} />
                  <DetailRow label="Low" value={fmtPrice(minuteBar.low)} />
                  <DetailRow label="Close" value={fmtPrice(minuteBar.close)} />
                  <DetailRow label="Volume" value={fmtVolume(minuteBar.volume)} />
                  <DetailRow label="VWAP" value={fmtPrice(minuteBar.vwap)} />
                </DetailSection>
              )}

              {/* Volume */}
              <DetailSection title="Volume">
                <DetailRow label="Today" value={fmtVolume(daily?.volume)} />
                <DetailRow label="Avg (20d)" value={fmtVolume(detail.avg_volume)} />
                <DetailRow
                  label="Rel. Volume"
                  value={detail.rel_volume != null ? `${detail.rel_volume}x` : '—'}
                  className={detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined}
                />
              </DetailSection>

              {/* Fundamentals */}
              {detail.fundamentals && (
                <DetailSection title="Fundamentals">
                  <DetailRow label="Market Cap" value={fmtMarketCap(detail.fundamentals.market_cap)} />
                  <DetailRow label="Shares Out." value={fmtVolume(detail.fundamentals.shares_outstanding)} />
                  <DetailRow label="Float" value={fmtVolume(detail.fundamentals.float_shares)} />
                  <DetailRow label="Short Interest" value={fmtVolume(detail.fundamentals.short_interest)} />
                  <DetailRow label="Short Ratio" value={detail.fundamentals.short_ratio != null ? detail.fundamentals.short_ratio.toFixed(2) : '—'} />
                  <DetailRow
                    label="Short % Float"
                    value={detail.fundamentals.short_percent_of_float != null
                      ? `${(detail.fundamentals.short_percent_of_float * 100).toFixed(1)}%`
                      : '—'}
                  />
                  <DetailRow label="P/E (TTM)" value={detail.fundamentals.pe_ratio != null ? detail.fundamentals.pe_ratio.toFixed(2) : '—'} />
                  <DetailRow label="Forward P/E" value={detail.fundamentals.forward_pe != null ? detail.fundamentals.forward_pe.toFixed(2) : '—'} />
                  <DetailRow label="EPS (TTM)" value={detail.fundamentals.eps != null ? `$${detail.fundamentals.eps.toFixed(2)}` : '—'} />
                  <DetailRow label="Beta" value={detail.fundamentals.beta != null ? detail.fundamentals.beta.toFixed(2) : '—'} />
                  <DetailRow
                    label="Dividend Yield"
                    value={detail.fundamentals.dividend_yield != null
                      ? `${(detail.fundamentals.dividend_yield * 100).toFixed(2)}%`
                      : '—'}
                  />
                  <DetailRow label="52W High" value={fmtPrice(detail.fundamentals.fifty_two_week_high)} />
                  <DetailRow label="52W Low" value={fmtPrice(detail.fundamentals.fifty_two_week_low)} />
                  {detail.fundamentals.sector && (
                    <DetailRow label="Sector" value={detail.fundamentals.sector} />
                  )}
                  {detail.fundamentals.industry && (
                    <DetailRow label="Industry" value={detail.fundamentals.industry} />
                  )}
                </DetailSection>
              )}

              {/* Asset Info */}
              {asset && (
                <DetailSection title="Asset Info">
                  <DetailRow label="Class" value={asset.asset_class || '—'} />
                  <DetailRow label="Tradable" value={<BoolBadge value={asset.tradable} />} />
                  <DetailRow label="Marginable" value={<BoolBadge value={asset.marginable} />} />
                  <DetailRow label="Shortable" value={<BoolBadge value={asset.shortable} />} />
                  <DetailRow label="Easy to Borrow" value={<BoolBadge value={asset.easy_to_borrow} />} />
                  <DetailRow label="Fractionable" value={<BoolBadge value={asset.fractionable} />} />
                  {asset.maintenance_margin_requirement != null && (
                    <DetailRow label="Margin Req." value={`${asset.maintenance_margin_requirement}%`} />
                  )}
                </DetailSection>
              )}

              {/* News */}
              {detail.news.length > 0 && (
                <DetailSection title={`News (${detail.news.length})`}>
                  <div className="news-list">
                    {detail.news.map((article, i) => (
                      <div key={i} className="news-card">
                        {article.images.find(img => img.size === 'thumb') && (
                          <img
                            className="news-thumb"
                            src={article.images.find(img => img.size === 'thumb')!.url}
                            alt=""
                            loading="lazy"
                          />
                        )}
                        <div className="news-card-body">
                          <a
                            className="news-headline"
                            href={article.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {article.headline}
                          </a>
                          {article.summary && (
                            <p className="news-summary">{article.summary}</p>
                          )}
                          <div className="news-meta">
                            <span>{article.source}</span>
                            {article.author && <span>· {article.author}</span>}
                            <span>· {timeAgo(article.created_at)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </DetailSection>
              )}

              {detail.news.length === 0 && (
                <DetailSection title="News">
                  <p className="detail-empty">No news today for {detail.symbol}.</p>
                </DetailSection>
              )}
            </div>
          </>
        )}
      </div>
    </>
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

// ── Main App ──────────────────────────────────────────────────────────────────

function App() {
  const [mode, setMode] = useState<Mode>('loading');
  const [health, setHealth] = useState<HealthStatus>({ status: 'loading', latency_ms: 0 });
  const [gappers, setGappers] = useState<Gapper[]>([]);
  const [gainers, setGainers] = useState<Gainer[]>([]);
  const [lastScan, setLastScan] = useState<number>(0);
  const [showSettings, setShowSettings] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [activeTab, setActiveTab] = useState<'gappers' | 'gainers'>('gappers');
  const [tabOverridden, setTabOverridden] = useState(false);
  const [gapperSubTab, setGapperSubTab] = useState<'all' | 'small_cap'>('all');
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [gainerSort, setGainerSort] = useState<SortConfig>({ key: '', dir: null });

  // Ticker detail state
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tickerDetail, setTickerDetail] = useState<TickerDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

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
      const [gr, gainRes] = await Promise.all([
        fetch(`${API_URL}/gappers`),
        fetch(`${API_URL}/gainers`),
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
    } catch {
      setHealth({ status: 'disconnected', latency_ms: 0, message: 'Backend unreachable' });
    }
  }, []);

  const fetchTickerDetail = useCallback(async (symbol: string) => {
    setSelectedSymbol(symbol);
    setDetailLoading(true);
    setTickerDetail(null);
    try {
      const res = await fetch(`${API_URL}/ticker/${symbol}`);
      if (res.ok) {
        const data = await res.json();
        setTickerDetail(data);
      }
    } catch {
      // silent — panel will show loading indefinitely but won't crash
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeDetail = useCallback(() => {
    setSelectedSymbol(null);
    setTickerDetail(null);
    setDetailLoading(false);
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

  const handleTabClick = (tab: 'gappers' | 'gainers') => {
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
                            onClick={() => fetchTickerDetail(g.symbol)}
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
                            onClick={() => fetchTickerDetail(g.symbol)}
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

      {/* ── Ticker Detail Panel ────────────────────────────────────── */}
      {selectedSymbol && (
        <TickerDetailPanel
          detail={tickerDetail}
          loading={detailLoading}
          onClose={closeDetail}
        />
      )}
    </div>
  );
}

function dotClass(status: string): string {
  if (status === 'connected') return 'connected';
  if (status === 'loading') return 'loading';
  return 'disconnected';
}

export default App;

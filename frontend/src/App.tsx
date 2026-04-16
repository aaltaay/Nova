import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';

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
import {
  SMALL_CAP_MIN, SMALL_CAP_MAX,
  NEWS_FLAME_HOT_HOURS, NEWS_FLAME_WARM_HOURS, NEWS_FLAME_MAX_HOURS,
  REL_VOLUME_HIGH,
  GAPPER_MIN_GAP_PCT,
  CATALYSTS_EXPERIMENTAL_LABEL,
  SCANNER_COLUMNS,
  QUOTE_CARD_TITLE,
  QUOTE_AVG_VOLUME_LABEL,
  QUOTE_BROKER_SECTION_TITLE,
  QUOTE_ASSET_LABELS,
  ALPACA_ASSET_ATTRIBUTE_LABELS,
  QUOTE_LISTING_FEED_VALUE,
} from './constants';

type Mode = 'premarket' | 'market' | 'afterhours' | 'closed' | 'loading';
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
  name?: string;
  exchange?: string;
  asset_class?: string;
  status?: string;
  tradable?: boolean;
  marginable?: boolean;
  shortable?: boolean;
  easy_to_borrow?: boolean;
  fractionable?: boolean;
  maintenance_margin_requirement?: number | null;
  margin_requirement_long?: string | null;
  margin_requirement_short?: string | null;
  attributes?: string[];
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
  if (context === 'afterhours') {
    return (
      <div className="empty-state">
        No after-hours movers with a gap of at least {GAPPER_MIN_GAP_PCT}% yet — scan running…
      </div>
    );
  }
  return <div className="empty-state">No gainers in the feed right now.</div>;
}

// ── useTickerStream hook ──────────────────────────────────────────────────────

function useTickerStream(symbol: string | null): { detail: TickerDetail | null; loading: boolean; refreshing: boolean; fetchFailed: boolean } {
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  // True while waiting for the initial frame for a new symbol (fast-data not yet arrived)
  const [refreshing, setRefreshing] = useState(false);
  // True after the WS closes without a successful `initial` (real failure, not StrictMode cleanup).
  const [fetchFailed, setFetchFailed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  // Mirrors whether `detail` is non-null so the effect can read it synchronously
  // without a stale closure — avoids calling setState inside another setState updater.
  const hasDetailRef = useRef(false);

  useEffect(() => {
    if (!symbol) {
      hasDetailRef.current = false;
      setDetail(null);
      setLoading(false);
      setRefreshing(false);
      setFetchFailed(false);
      return;
    }

    // `cancelled` guards against the old WebSocket's onclose/onerror firing
    // after cleanup (React StrictMode double-mount, or rapid symbol changes).
    let cancelled = false;
    let initialReceived = false;

    setFetchFailed(false);

    // Show the full spinner only when there is nothing to display yet.
    // When switching symbols, keep the previous detail visible and use the
    // slim refreshing bar. All setters called directly — no side effects
    // inside updater functions (React would call those twice in StrictMode).
    setLoading(!hasDetailRef.current);
    setRefreshing(true);

    const ws = new WebSocket(`${WS_URL}/ticker/${symbol}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      if (cancelled) return;
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'initial') {
          // Phase 1: fast data (asset + snapshot) — render immediately
          const { type: _t, ...data } = msg;
          initialReceived = true;
          hasDetailRef.current = true;
          setDetail(data as TickerDetail);
          setLoading(false);
          setRefreshing(false);
          setFetchFailed(false);
        } else if (msg.type === 'detail_update') {
          // Phase 2: slow data (news + fundamentals + fresh avg/rel volume)
          setDetail(prev => {
            if (!prev) return prev;
            return {
              ...prev,
              news: msg.news ?? prev.news,
              fundamentals: msg.fundamentals ?? prev.fundamentals,
              avg_volume: msg.avg_volume ?? prev.avg_volume,
              rel_volume: msg.rel_volume ?? prev.rel_volume,
            };
          });
        } else if (msg.type === 'trade_update') {
          const update = msg as TickerTradeUpdate;
          setDetail(prev => {
            if (!prev) return prev;
            const prevClose = prev.snapshot?.prev_daily_bar?.close ?? null;
            const newPrice = update.price;
            const newSnapshot = {
              ...prev.snapshot,
              latest_trade: {
                price: newPrice,
                size: update.size ?? prev.snapshot?.latest_trade?.size ?? null,
                timestamp: update.timestamp ?? prev.snapshot?.latest_trade?.timestamp ?? null,
                exchange: prev.snapshot?.latest_trade?.exchange ?? null,
              },
            };
            const dailyVol = prev.snapshot?.daily_bar?.volume ?? null;
            const avgVol = prev.avg_volume;
            const relVol = dailyVol != null && avgVol != null && avgVol > 0
              ? Math.round((dailyVol / avgVol) * 100) / 100
              : prev.rel_volume;
            void prevClose;
            return { ...prev, snapshot: newSnapshot, rel_volume: relVol };
          });
        }
        // ignore 'ping' messages
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {
      if (!cancelled) {
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) setFetchFailed(true);
      }
    };
    ws.onclose = () => {
      if (!cancelled) {
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) setFetchFailed(true);
      }
    };

    return () => {
      cancelled = true;
      wsRef.current = null;
      ws.close();
    };
  }, [symbol]);

  return { detail, loading, refreshing, fetchFailed };
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

function fmtYesNo(v: boolean | undefined): string {
  if (v === true) return 'Yes';
  if (v === false) return 'No';
  return '—';
}

function fmtMaintMarginPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${Number(v)}%`;
}

function fmtMarginReqString(v: string | null | undefined): string {
  if (v == null || v === '') return '—';
  const s = String(v).trim();
  return s.endsWith('%') ? s : `${s}%`;
}

function formatAssetAttributeList(attrs: string[] | undefined): string {
  if (!attrs?.length) return '—';
  return attrs
    .map(a => ALPACA_ASSET_ATTRIBUTE_LABELS[a] ?? a.replace(/_/g, ' '))
    .join(', ');
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
  const news = detail.news ?? [];
  const visibleNews = newsExpanded ? news : news.slice(0, NEWS_DEFAULT);

  // Gap % from prev close to today's open (or current price if no open)
  const todayOpen = daily?.open ?? null;
  const gapPct = (todayOpen != null && prevClose != null && prevClose !== 0)
    ? (todayOpen - prevClose) / prevClose
    : null;

  return (
    <div className="cq-root">
      <div className="cq-section-title cq-card-title">{QUOTE_CARD_TITLE}</div>
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
      {news.length > 0 && (
        <div className="cq-news-section">
          <div className="cq-news-header">
            <span className="cq-news-title">News Headline</span>
            {news.length > NEWS_DEFAULT && (
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

        <CompactGridCell label={QUOTE_AVG_VOLUME_LABEL} value={fmtVolume(detail.avg_volume ?? null)} />
        <CompactGridCell
          label="Relative Volume (Daily)"
          value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
          valueClass={detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined}
        />

        <CompactGridCell label="Relative Volume (5 min %)" value="—" />
        <CompactGridCell label="Volume In 5 Minutes" value="—" />

        <CompactGridCell
          label="Gap(%)"
          value={gapPct != null ? `${(gapPct * 100).toFixed(2)}` : '—'}
          valueClass={gapPct != null ? (gapPct >= 0 ? 'positive' : 'negative') : undefined}
        />
        <CompactGridCell label="Open" value={fmtPrice(daily?.open)} />

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

      <div className="cq-section-title">{QUOTE_BROKER_SECTION_TITLE}</div>
      <div className="cq-grid cq-grid-broker">
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.status}
          value={asset?.status ? String(asset.status) : '—'}
        />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.tradable}
          value={fmtYesNo(asset?.tradable)}
          valueClass={asset?.tradable === false ? 'negative' : undefined}
        />

        <CompactGridCell
          label={QUOTE_ASSET_LABELS.assetClass}
          value={asset?.asset_class ? String(asset.asset_class) : '—'}
        />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.shortable}
          value={fmtYesNo(asset?.shortable)}
        />

        <CompactGridCell
          label={QUOTE_ASSET_LABELS.marginable}
          value={fmtYesNo(asset?.marginable)}
        />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.fractionable}
          value={fmtYesNo(asset?.fractionable)}
        />

        <CompactGridCell
          label={QUOTE_ASSET_LABELS.easyToBorrow}
          value={fmtYesNo(asset?.easy_to_borrow)}
        />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.maintMargin}
          value={fmtMaintMarginPct(asset?.maintenance_margin_requirement ?? null)}
        />

        <CompactGridCell
          label={QUOTE_ASSET_LABELS.marginLong}
          value={fmtMarginReqString(asset?.margin_requirement_long ?? null)}
        />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.marginShort}
          value={fmtMarginReqString(asset?.margin_requirement_short ?? null)}
        />

        <CompactGridCell
          label={QUOTE_ASSET_LABELS.listingFeed}
          value={QUOTE_LISTING_FEED_VALUE}
        />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.attributes}
          value={formatAssetAttributeList(asset?.attributes)}
          valueClass="cq-value-flags"
        />
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
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(selectedSymbol);

  // One render happens after selecting a symbol before the WS effect runs; without this,
  // loading/refreshing are still false and detail is null → a false "No data" flash.
  const awaitingPreEffectFrame =
    !!selectedSymbol && detail == null && !loading && !refreshing && !fetchFailed;
  const showFullSpinner = loading || awaitingPreEffectFrame;

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
        {showFullSpinner && (
          <div className="detail-loading">
            <div className="detail-loading-spinner" />
            <span>Loading…</span>
          </div>
        )}
        {!showFullSpinner && selectedSymbol && refreshing && detail && (
          <div className="detail-refreshing-bar">
            <div className="detail-loading-spinner detail-loading-spinner--small" />
            <span>Updating {selectedSymbol}…</span>
          </div>
        )}
        {!showFullSpinner && selectedSymbol && detail && (
          <div className="detail-body">
            <TickerDetailContent detail={detail} />
          </div>
        )}
        {!showFullSpinner && fetchFailed && !detail && selectedSymbol && (
          <div className="detail-empty">No data found for {selectedSymbol}.</div>
        )}
        {!showFullSpinner && !selectedSymbol && (
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
  afterhours: 'After Hours',
  closed: 'Market Closed',
};

const API_URL = 'http://localhost:8000/api';
const WS_URL = 'ws://localhost:8000/ws';

// ── Scanner Table ─────────────────────────────────────────────────────────────

interface ScannerTableProps {
  columns: [string, string][];
  data: ScannerRow[];
  sortState: SortConfig;
  onSort: (key: string) => void;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
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

function ScannerTable({ columns, data, sortState, onSort, selectedSymbol, onSelect }: ScannerTableProps) {
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
                    <button
                      className={`symbol-btn${selectedSymbol === row.symbol ? ' active' : ''}`}
                      onClick={() => onSelect(row.symbol)}
                    >
                      {row.symbol}
                    </button>
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
  const [activeTab, setActiveTab] = useState<'gappers' | 'movers' | 'afterhours' | 'catalysts'>('gappers');
  const [tabOverridden, setTabOverridden] = useState(false);
  const [gapperSubTab, setGapperSubTab] = useState<'all' | 'small_cap'>('all');
  const [gapperSort, setGapperSort] = useState<SortConfig>({ key: '', dir: null });
  const [moverSort, setMoverSort] = useState<SortConfig>({ key: '', dir: null });
  const [afterhoursSort, setAfterhoursSort] = useState<SortConfig>({ key: '', dir: null });
  const [catalystSort, setCatalystSort] = useState<SortConfig>({ key: '', dir: null });

  // Catalysts tab state
  const [catalysts, setCatalysts] = useState<Catalyst[]>([]);

  // Ticker detail state (side panel)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  // Settings form state
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.alpaca.markets');

  // History / time-travel state
  const [historyDate, setHistoryDate] = useState<string | null>(null); // null = live
  const [historyDates, setHistoryDates] = useState<string[]>([]);

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
        if (data.health) setHealth(data.health);
        if (data.mode) setMode(data.mode as Mode);
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
    } catch {
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

  const handleTabClick = (tab: 'gappers' | 'movers' | 'afterhours' | 'catalysts') => {
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

  function fmtHistoryDate(dateStr: string): string {
    // "2026-04-14" → "Mon, Apr 14"
    const [y, m, d] = dateStr.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  }

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

  return (
    <div className="container">
      <div className="main-col">
      <header>
        <div className="header-left">
          <div className="brand">
            <NovaLogo />
            <div className="brand-text">
              <span className="brand-wordmark">NOVA</span>
              <span className="brand-tagline">Stock Scanner</span>
            </div>
          </div>
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
          <select
            className={`history-select${historyDate ? ' history-select--active' : ''}`}
            value={historyDate ?? ''}
            onChange={handleHistoryChange}
            title="Browse historical snapshots"
          >
            <option value="">Today (Live)</option>
            {historyDates.map(d => (
              <option key={d} value={d}>{fmtHistoryDate(d)}</option>
            ))}
          </select>
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
            className={`tab ${activeTab === 'movers' ? 'active' : ''}`}
            onClick={() => handleTabClick('movers')}
          >
            Movers
            {movers.length > 0 && <span className="tab-count">{movers.length}</span>}
          </button>
          <button
            className={`tab ${activeTab === 'afterhours' ? 'active' : ''}`}
            onClick={() => handleTabClick('afterhours')}
          >
            After Hours
            {afterhours.length > 0 && <span className="tab-count">{afterhours.length}</span>}
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
          {!historyDate && secondsAgo != null && (
            <span className="scan-age">updated {secondsAgo}s ago</span>
          )}
        </div>

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
              />
            ) : (
              <EmptyState health={health} context={mode === 'market' ? 'afterhours' : mode} />
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

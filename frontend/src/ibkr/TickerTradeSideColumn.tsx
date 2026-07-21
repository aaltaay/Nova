/** Compact side column for the full ticker trading page — quote/stats/news/depth,
 * not a second full clone of the sidebar stack. */
import {
  QUOTE_RVOL_DAILY_LABEL,
  QUOTE_RVOL_DAILY_TITLE,
  REL_VOLUME_HIGH,
  TICKER_TRADE_DEPTH_LEVELS,
  TICKER_TRADE_SIDE_NEWS_COUNT,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import { formatShareQty } from '../utils/formatShareQty';
import {
  fmtMarketCap,
  fmtPct,
  fmtPrice,
  fmtSessionPrice,
  fmtVolume,
  sessionPriceOrNull,
  timeAgo,
} from '../utils/quoteFormat';
import { DepthAndTape } from './DepthAndTape';
import type { IbkrMode, IbkrPosition } from './types';

interface Props {
  detail: TickerDetail;
  position: IbkrPosition | null;
  ibkrConnected: boolean;
  mode: IbkrMode;
}

function Stat({
  label,
  value,
  valueClass,
  title,
}: {
  label: string;
  value: string;
  valueClass?: string;
  title?: string;
}) {
  return (
    <div className="trade-side-stat" title={title}>
      <span className="trade-side-stat-label">{label}</span>
      <span className={`trade-side-stat-value${valueClass ? ` ${valueClass}` : ''}`}>{value}</span>
    </div>
  );
}

export function TickerTradeSideColumn({ detail, position, ibkrConnected, mode }: Props) {
  const snap = detail.snapshot;
  const asset = detail.asset;
  const daily = snap?.daily_bar;
  const prevClose = snap?.prev_close ?? snap?.prev_daily_bar?.close ?? null;
  const todayOpen = sessionPriceOrNull(daily?.open);
  const gapPct =
    todayOpen != null && prevClose != null && prevClose !== 0
      ? (todayOpen - prevClose) / prevClose
      : null;

  const descParts: string[] = [];
  if (asset?.name) descParts.push(asset.name);
  if (asset?.exchange) descParts.push(asset.exchange);
  if (detail.fundamentals?.sector) descParts.push(detail.fundamentals.sector);

  const news = (detail.news ?? []).slice(0, TICKER_TRADE_SIDE_NEWS_COUNT);
  const modeLabel = mode === 'paper' ? 'PAPER' : mode === 'live' ? 'LIVE' : 'OFFLINE';

  return (
    <aside className="ticker-trade-side" aria-label="Ticker information">
      <div className="ticker-trade-side-mode">
        <span className={`ibkr-mode-badge ibkr-mode-${mode}`}>{modeLabel}</span>
        <span className="ticker-trade-side-mode-hint">
          {ibkrConnected ? 'IBKR connected' : 'IBKR disconnected'}
        </span>
      </div>

      {descParts.length > 0 && (
        <div className="ticker-trade-side-desc">{descParts.join(' · ')}</div>
      )}

      <div className="ticker-trade-side-section-title">Key stats</div>
      <div className="ticker-trade-side-stats">
        <Stat label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
        <Stat label="Volume" value={fmtVolume(daily?.volume)} />
        <Stat
          label={QUOTE_RVOL_DAILY_LABEL}
          value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
          valueClass={
            detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined
          }
          title={QUOTE_RVOL_DAILY_TITLE}
        />
        <Stat
          label="Gap %"
          value={gapPct != null ? fmtPct(gapPct) : '—'}
          valueClass={gapPct != null ? (gapPct >= 0 ? 'positive' : 'negative') : undefined}
        />
        <Stat label="Open" value={fmtSessionPrice(daily?.open)} />
        <Stat label="Prev close" value={fmtPrice(prevClose)} />
        <Stat label="High" value={fmtSessionPrice(daily?.high)} />
        <Stat label="Low" value={fmtSessionPrice(daily?.low)} />
        <Stat label="Mkt cap" value={fmtMarketCap(detail.fundamentals?.market_cap)} />
        <Stat label="Short int" value={fmtVolume(detail.fundamentals?.short_interest)} />
      </div>

      {position && (
        <>
          <div className="ticker-trade-side-section-title">Open position</div>
          <div className="ticker-trade-side-position">
            <Stat label="Qty" value={formatShareQty(position.qty)} />
            <Stat label="Avg cost" value={fmtPrice(position.avg_cost)} />
            <Stat label="Mkt" value={fmtPrice(position.market_price)} />
            <Stat
              label="uPnL"
              value={fmtPrice(position.unrealized_pnl)}
              valueClass={
                position.unrealized_pnl != null
                  ? position.unrealized_pnl >= 0
                    ? 'positive'
                    : 'negative'
                  : undefined
              }
            />
          </div>
        </>
      )}

      {news.length > 0 && (
        <>
          <div className="ticker-trade-side-section-title">News</div>
          <ul className="ticker-trade-side-news">
            {news.map((article, i) => (
              <li key={i}>
                <a href={article.url} target="_blank" rel="noopener noreferrer">
                  {article.headline}
                </a>
                <span className="ticker-trade-side-news-age">{timeAgo(article.created_at)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {ibkrConnected && (
        <>
          <div className="ticker-trade-side-section-title">
            Level 2{' '}
            <span className="na-muted">(top {TICKER_TRADE_DEPTH_LEVELS})</span>
          </div>
          <div className="ticker-trade-side-depth">
            <DepthAndTape symbol={detail.symbol} />
          </div>
        </>
      )}
    </aside>
  );
}

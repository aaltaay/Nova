/** Fundamentals + news + broker grid for a ticker; optional panel chart / stacked layout. */
import { useEffect, useState } from 'react';
import { TickerChart } from '../TickerChart';
import { CompactGridCell } from './CompactGridCell';
import { NewsHeadlineSection } from './NewsHeadlineSection';
import { TickerBrokerGrid } from './TickerBrokerGrid';
import { TickerDataSources } from './TickerDataSources';
import { TickerWatchlistStrip } from './TickerWatchlistStrip';
import { DepthAndTape } from '../ibkr/DepthAndTape';
import {
  API_BASE_URL,
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
  QUOTE_AVG_VOLUME_LABEL,
  QUOTE_CARD_TITLE,
  REL_VOLUME_HIGH,
  TICKER_L2_SOURCE_LABEL,
  TICKER_TRADE_DEPTH_LEVELS,
} from '../constants';
import type { WatchlistEntry } from '../strategy/types';
import type { TickerDetail } from '../types/ticker';
import {
  fmtMarketCap,
  fmtPct,
  fmtPrice,
  fmtSessionPrice,
  fmtTimestamp,
  fmtVolume,
  sessionPriceOrNull,
  timeAgo,
} from '../utils/quoteFormat';

const API_URL = `${API_BASE_URL}/api`;

interface Props {
  detail: TickerDetail;
  /**
   * Panel selection source of truth. Level 2 / live surfaces must bind to this,
   * never a stale detail.symbol from a previous ticker.
   */
  selectedSymbol?: string;
  /** When true, omit the quote header (symbol/price) — parent page already shows it. */
  hideHeader?: boolean;
  /** When true, render the panel-height chart (side panel). */
  showChart?: boolean;
  /** Side-by-side columns when width allows (quote | fundamentals under chart). */
  layout?: 'stack' | 'columns';
  /** Five Pillars / sub-scores for this symbol when ranked on the watchlist. */
  watchlistEntry?: WatchlistEntry | null;
  /** IB Gateway connection state — gates the Level 2 depth section below the quote. */
  ibkrConnected?: boolean;
  /** Scanner discovery provider ('alpaca' | 'ibkr') — drives Data sources attribution. */
  discoveryProvider?: string;
  /** Alpaca market-data tier ('iex' | 'sip') — shown on quote/chart attribution. */
  alpacaFeed?: string;
}

export function TickerDetailContent({
  detail,
  selectedSymbol,
  hideHeader = false,
  showChart = false,
  layout = 'stack',
  watchlistEntry = null,
  ibkrConnected = false,
  discoveryProvider = DISCOVERY_PROVIDER_DEFAULT,
  alpacaFeed = DATA_FEED_DEFAULT,
}: Props) {
  const depthSymbol = (selectedSymbol ?? detail.symbol).toUpperCase();
  const detailMatchesSelection = detail.symbol.toUpperCase() === depthSymbol;
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/hod-momo/blocklist`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!cancelled) setBlocked(!!data?.symbols?.includes(detail.symbol));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [detail.symbol]);

  function onToggleBlock() {
    if (blocked) {
      fetch(`${API_URL}/hod-momo/blocklist/${detail.symbol}`, { method: 'DELETE' })
        .then(r => { if (r.ok) setBlocked(false); })
        .catch(() => {});
      return;
    }
    if (!window.confirm(
      `Block ${detail.symbol}?\n\nThis removes it from every scanner (Gappers, Movers, ` +
      'After-Hours, News Catalysts) and HOD Momo alerts until you unblock it.'
    )) {
      return;
    }
    fetch(`${API_URL}/hod-momo/blocklist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: detail.symbol }),
    }).then(r => { if (r.ok) setBlocked(true); }).catch(() => {});
  }

  const snap = detail.snapshot;
  const asset = detail.asset;
  const trade = snap?.latest_trade;
  const daily = snap?.daily_bar;
  const prevClose = snap?.prev_close ?? snap?.prev_daily_bar?.close ?? null;
  // IBKR discovery: one live price vs IBKR prev_close — same math as the scanner row.
  // Alpaca discovery keeps Webull two-line Pre:/After: layout.
  const useIbkrUnifiedQuote = discoveryProvider === 'ibkr';
  const isExtendedHours =
    !useIbkrUnifiedQuote && (detail.mode === 'premarket' || detail.mode === 'afterhours');
  const sessionClose = snap?.session_close ?? null;
  const sessionPrevClose = snap?.session_prev_close ?? null;
  const livePrice = trade?.price ?? daily?.close ?? null;
  const mainPrice = useIbkrUnifiedQuote
    ? livePrice
    : (isExtendedHours ? sessionClose : livePrice);
  const mainPrevRef = useIbkrUnifiedQuote
    ? prevClose
    : (isExtendedHours ? sessionPrevClose : prevClose);
  const mainChangeAbs = (mainPrice != null && mainPrevRef != null) ? mainPrice - mainPrevRef : null;
  const mainChangePct = (mainChangeAbs != null && mainPrevRef) ? mainChangeAbs / mainPrevRef : null;
  const extPrice = isExtendedHours ? livePrice : null;
  const extChangeAbs = (extPrice != null && sessionClose != null) ? extPrice - sessionClose : null;
  const extChangePct = (extChangeAbs != null && sessionClose) ? extChangeAbs / sessionClose : null;
  const extLabel = detail.mode === 'premarket' ? 'Pre' : 'After';
  const extIsPositive = (extChangePct ?? 0) >= 0;
  const isPositive = isExtendedHours ? extIsPositive : (mainChangePct ?? 0) >= 0;
  const lastUpdated = trade?.timestamp ?? snap?.latest_quote?.timestamp ?? null;

  const descParts: string[] = [];
  if (asset?.name) descParts.push(asset.name);
  if (asset?.exchange) descParts.push(asset.exchange);
  if (detail.fundamentals?.sector) descParts.push(detail.fundamentals.sector);
  if (detail.fundamentals?.industry) descParts.push(detail.fundamentals.industry);

  const news = detail.news ?? [];
  const todayOpen = sessionPriceOrNull(daily?.open);
  const gapPct = (todayOpen != null && prevClose != null && prevClose !== 0)
    ? (todayOpen - prevClose) / prevClose
    : null;

  const columns = layout === 'columns';
  const chartEl = showChart ? (
    <TickerChart
      symbol={detail.symbol}
      variant="panel"
      lastTrade={
        trade?.price != null
          ? { price: trade.price, timestamp: trade.timestamp ?? null }
          : undefined
      }
    />
  ) : null;

  const quoteHeader = (
    <>
      {!hideHeader && (
        <>
          <div className="cq-section-title cq-card-title">{QUOTE_CARD_TITLE}</div>
          <div className="cq-header">
            <div className="cq-symbol-row">
              <span className="cq-symbol">{detail.symbol}</span>
              {(mainChangeAbs != null || extChangeAbs != null) && (
                <span className="cq-trend">{isPositive ? '▲' : '▼'}</span>
              )}
              <button
                className={`cq-block-btn${blocked ? ' cq-block-btn--blocked' : ''}`}
                onClick={onToggleBlock}
                title={blocked ? 'Remove from HOD Momo blocklist' : 'Add to HOD Momo blocklist'}
              >{blocked ? 'Unblock' : 'Block'}</button>
            </div>
            {mainPrice != null && (
              <div className="cq-price-row">
                <span className="cq-price">{mainPrice.toFixed(2)}</span>
                {mainChangeAbs != null && (
                  <span className={`cq-change ${(mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}>
                    {mainChangeAbs >= 0 ? '+' : ''}{mainChangeAbs.toFixed(2)} ({fmtPct(mainChangePct)})
                  </span>
                )}
              </div>
            )}
            {isExtendedHours && extPrice != null && (
              <div className="cq-ext-row">
                <span className="cq-ext-label">{extLabel}:</span>
                <span className="cq-ext-price">{extPrice.toFixed(2)}</span>
                {extChangeAbs != null && (
                  <span className={`cq-ext-change ${extIsPositive ? 'positive' : 'negative'}`}>
                    {extChangeAbs >= 0 ? '+' : ''}{extChangeAbs.toFixed(2)} ({fmtPct(extChangePct)})
                  </span>
                )}
              </div>
            )}
          </div>
        </>
      )}
      {hideHeader && (
        <div className="cq-symbol-row cq-detail-actions">
          <button
            className={`cq-block-btn${blocked ? ' cq-block-btn--blocked' : ''}`}
            onClick={onToggleBlock}
            title={blocked ? 'Remove from HOD Momo blocklist' : 'Add to HOD Momo blocklist'}
          >{blocked ? 'Unblock' : 'Block'}</button>
        </div>
      )}
      {descParts.length > 0 && (
        <div className="cq-description">{descParts.join(' | ')}</div>
      )}
      {lastUpdated && (
        <div className="cq-timestamp">Last updated on {fmtTimestamp(lastUpdated)}</div>
      )}
    </>
  );

  const keyStats = (
    <div className="cq-grid cq-grid-key">
      <CompactGridCell label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
      <CompactGridCell label="Volume" value={fmtVolume(daily?.volume)} />
      <CompactGridCell label={QUOTE_AVG_VOLUME_LABEL} value={fmtVolume(detail.avg_volume ?? null)} />
      <CompactGridCell
        label="Relative Volume (Daily)"
        value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
        valueClass={detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined}
      />
      <CompactGridCell
        label="Gap(%)"
        value={gapPct != null ? `${(gapPct * 100).toFixed(2)}` : '—'}
        valueClass={gapPct != null ? (gapPct >= 0 ? 'positive' : 'negative') : undefined}
      />
      <CompactGridCell label="Open" value={fmtSessionPrice(daily?.open)} />
      <CompactGridCell label="Previous Close" value={fmtPrice(prevClose)} />
      <CompactGridCell label="High Price" value={fmtSessionPrice(daily?.high)} />
      <CompactGridCell label="Low Price" value={fmtSessionPrice(daily?.low)} />
    </div>
  );

  const depthSection = ibkrConnected && detailMatchesSelection ? (
    <div className="cq-depth-stack">
      <div className="cq-section-title">
        Level 2{' '}
        <span className="na-muted">
          (top {TICKER_TRADE_DEPTH_LEVELS} · {TICKER_L2_SOURCE_LABEL})
        </span>
      </div>
      <DepthAndTape key={depthSymbol} symbol={depthSymbol} />
    </div>
  ) : null;

  const dataSources = (
    <TickerDataSources
      discoveryProvider={discoveryProvider}
      alpacaFeed={alpacaFeed}
      ibkrConnected={ibkrConnected}
    />
  );

  const fundGrid = (
    <div className="cq-grid">
      {!columns && (
        <>
          <CompactGridCell label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
          <CompactGridCell label="Volume" value={fmtVolume(daily?.volume)} />
          <CompactGridCell label={QUOTE_AVG_VOLUME_LABEL} value={fmtVolume(detail.avg_volume ?? null)} />
          <CompactGridCell
            label="Relative Volume (Daily)"
            value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
            valueClass={detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined}
          />
          <CompactGridCell
            label="Relative Volume (5 min)"
            value={detail.rvol_5min != null ? `${detail.rvol_5min.toFixed(2)}x` : '—'}
            valueClass={
              detail.rvol_5min != null && detail.rvol_5min >= REL_VOLUME_HIGH ? 'positive' : undefined
            }
          />
          <CompactGridCell
            label="Volume In 5 Minutes"
            value={detail.volume_in_5min != null ? fmtVolume(detail.volume_in_5min) : '—'}
          />
          <CompactGridCell
            label="Gap(%)"
            value={gapPct != null ? `${(gapPct * 100).toFixed(2)}` : '—'}
            valueClass={gapPct != null ? (gapPct >= 0 ? 'positive' : 'negative') : undefined}
          />
          <CompactGridCell label="Open" value={fmtSessionPrice(daily?.open)} />
          <CompactGridCell label="Previous Close" value={fmtPrice(prevClose)} />
          <CompactGridCell label="High Price" value={fmtSessionPrice(daily?.high)} />
          <CompactGridCell label="Low Price" value={fmtSessionPrice(daily?.low)} />
        </>
      )}
      <CompactGridCell label="High In 52 Weeks" value={fmtPrice(detail.fundamentals?.fifty_two_week_high)} />
      <CompactGridCell label="Low In 52 Weeks" value={fmtPrice(detail.fundamentals?.fifty_two_week_low)} />
      <CompactGridCell label="Short Interest" value={fmtVolume(detail.fundamentals?.short_interest)} />
      <CompactGridCell label="Earnings Date" value={detail.fundamentals?.earnings_date ?? '—'} />
      <CompactGridCell label="Market Cap" value={fmtMarketCap(detail.fundamentals?.market_cap)} />
      <CompactGridCell label="Industry" value={detail.fundamentals?.industry ?? '—'} />
      <CompactGridCell label="Sector" value={detail.fundamentals?.sector ?? '—'} />
      <CompactGridCell label="Recent Split" value={detail.fundamentals?.recent_split ?? '—'} />
      <CompactGridCell label="Exchange Group" value={asset?.exchange ?? '—'} />
    </div>
  );

  const brokerGrid = <TickerBrokerGrid asset={asset} />;

  if (columns) {
    // Stacked sidebar: chart → news row → watchlist strip → quote | fundamentals.
    return (
      <div className="cq-root cq-root--stacked">
        <div className="cq-col cq-col--chart">{chartEl}</div>
        <div className="cq-news-row">
          <NewsHeadlineSection news={news} newsImpact={detail.news_impact} timeAgo={timeAgo} />
        </div>
        <TickerWatchlistStrip entry={watchlistEntry} />
        {depthSection}
        <div className="cq-info-row cq-info-row--two">
          <div className="cq-col cq-col--quote">
            {quoteHeader}
            {keyStats}
          </div>
          <div className="cq-col cq-col--fund">
            <div className="cq-section-title">Fundamentals</div>
            {fundGrid}
            {brokerGrid}
            {dataSources}
            {lastUpdated && (
              <div className="cq-timestamp cq-timestamp-bottom">Last updated on {fmtTimestamp(lastUpdated)}</div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="cq-root">
      {quoteHeader}
      {depthSection}
      {chartEl}
      <NewsHeadlineSection news={news} newsImpact={detail.news_impact} timeAgo={timeAgo} />
      {fundGrid}
      {brokerGrid}
      {dataSources}
      {lastUpdated && (
        <div className="cq-timestamp cq-timestamp-bottom">Last updated on {fmtTimestamp(lastUpdated)}</div>
      )}
    </div>
  );
}

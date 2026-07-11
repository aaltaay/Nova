/** Fundamentals + news + broker grid for a ticker (chart lives on the parent page). */
import { useEffect, useState } from 'react';
import { NewsHeadlineSection } from './NewsHeadlineSection';
import {
  API_BASE_URL,
  QUOTE_AVG_VOLUME_LABEL,
  QUOTE_ASSET_LABELS,
  QUOTE_BROKER_SECTION_TITLE,
  QUOTE_CARD_TITLE,
  QUOTE_LISTING_FEED_VALUE,
  REL_VOLUME_HIGH,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import {
  fmtMaintMarginPct,
  fmtMarginReqString,
  fmtMarketCap,
  fmtPct,
  fmtPrice,
  fmtTimestamp,
  fmtVolume,
  fmtYesNo,
  formatAssetAttributeList,
  timeAgo,
} from '../utils/quoteFormat';

const API_URL = `${API_BASE_URL}/api`;

function CompactGridCell({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="cq-cell">
      <span className="cq-label">{label}</span>
      <span className={`cq-value${valueClass ? ' ' + valueClass : ''}`}>{value}</span>
    </div>
  );
}

interface Props {
  detail: TickerDetail;
  /** When true, omit the quote header (symbol/price) — parent page already shows it. */
  hideHeader?: boolean;
}

export function TickerDetailContent({ detail, hideHeader = false }: Props) {
  const [blocked, setBlocked] = useState(false);
  useEffect(() => { setBlocked(false); }, [detail.symbol]);

  function onBlock() {
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
  const isExtendedHours = detail.mode === 'premarket' || detail.mode === 'afterhours';
  const sessionClose = snap?.session_close ?? null;
  const sessionPrevClose = snap?.session_prev_close ?? null;
  const livePrice = trade?.price ?? daily?.close ?? null;
  const mainPrice = isExtendedHours ? sessionClose : livePrice;
  const mainPrevRef = isExtendedHours ? sessionPrevClose : prevClose;
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
  const todayOpen = daily?.open ?? null;
  const gapPct = (todayOpen != null && prevClose != null && prevClose !== 0)
    ? (todayOpen - prevClose) / prevClose
    : null;

  return (
    <div className="cq-root">
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
                onClick={onBlock}
                disabled={blocked}
                title="Add to HOD Momo blocklist"
              >{blocked ? 'Blocked' : 'Block'}</button>
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
            onClick={onBlock}
            disabled={blocked}
            title="Add to HOD Momo blocklist"
          >{blocked ? 'Blocked' : 'Block'}</button>
        </div>
      )}

      {descParts.length > 0 && (
        <div className="cq-description">{descParts.join(' | ')}</div>
      )}

      {lastUpdated && (
        <div className="cq-timestamp">Last updated on {fmtTimestamp(lastUpdated)}</div>
      )}

      <NewsHeadlineSection
        news={news}
        newsImpact={detail.news_impact}
        timeAgo={timeAgo}
      />

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
        <CompactGridCell label="Earnings Date" value={detail.fundamentals?.earnings_date ?? '—'} />
        <CompactGridCell label="Market Cap" value={fmtMarketCap(detail.fundamentals?.market_cap)} />
        <CompactGridCell label="Industry" value={detail.fundamentals?.industry ?? '—'} />
        <CompactGridCell label="Sector" value={detail.fundamentals?.sector ?? '—'} />
        <CompactGridCell label="Recent Split" value={detail.fundamentals?.recent_split ?? '—'} />
        <CompactGridCell label="Exchange Group" value={asset?.exchange ?? '—'} />
      </div>

      <div className="cq-section-title">{QUOTE_BROKER_SECTION_TITLE}</div>
      <div className="cq-grid cq-grid-broker">
        <CompactGridCell label={QUOTE_ASSET_LABELS.status} value={asset?.status ? String(asset.status) : '—'} />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.tradable}
          value={fmtYesNo(asset?.tradable)}
          valueClass={asset?.tradable === false ? 'negative' : undefined}
        />
        <CompactGridCell label={QUOTE_ASSET_LABELS.assetClass} value={asset?.asset_class ? String(asset.asset_class) : '—'} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.shortable} value={fmtYesNo(asset?.shortable)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.marginable} value={fmtYesNo(asset?.marginable)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.fractionable} value={fmtYesNo(asset?.fractionable)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.easyToBorrow} value={fmtYesNo(asset?.easy_to_borrow)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.maintMargin} value={fmtMaintMarginPct(asset?.maintenance_margin_requirement ?? null)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.marginLong} value={fmtMarginReqString(asset?.margin_requirement_long ?? null)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.marginShort} value={fmtMarginReqString(asset?.margin_requirement_short ?? null)} />
        <CompactGridCell label={QUOTE_ASSET_LABELS.listingFeed} value={QUOTE_LISTING_FEED_VALUE} />
        <CompactGridCell
          label={QUOTE_ASSET_LABELS.attributes}
          value={formatAssetAttributeList(asset?.attributes)}
          valueClass="cq-value-flags"
        />
      </div>

      {lastUpdated && (
        <div className="cq-timestamp cq-timestamp-bottom">Last updated on {fmtTimestamp(lastUpdated)}</div>
      )}
    </div>
  );
}

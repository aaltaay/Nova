/** Broker/listing attribute grid (Alpaca asset flags) shown under the fundamentals grid. */
import { CompactGridCell } from './CompactGridCell';
import {
  QUOTE_ASSET_LABELS,
  QUOTE_BROKER_SECTION_TITLE,
  QUOTE_LISTING_FEED_VALUE,
} from '../constants';
import type { AssetInfo } from '../types/ticker';
import {
  fmtMaintMarginPct,
  fmtMarginReqString,
  fmtYesNo,
  formatAssetAttributeList,
} from '../utils/quoteFormat';

interface Props {
  asset: AssetInfo | null | undefined;
}

export function TickerBrokerGrid({ asset }: Props) {
  return (
    <>
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
    </>
  );
}

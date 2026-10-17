/** Compact Float / Vol / RVOL / Gap / High / Low row for the Stock Quote card. */
import { CompactGridCell } from '../components/CompactGridCell';
import {
  QUOTE_RVOL_DAILY_LABEL,
  QUOTE_RVOL_DAILY_TITLE,
  REL_VOLUME_HIGH,
} from '../constants';
import { QUOTE_GAP_OPEN_TITLE } from '../constantGroups/trader_view';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import type { TickerDetail } from '../types/ticker';
import { fmtSessionPrice, fmtVolume, pctToneClass } from '../utils/quoteFormat';
import { replayDayLabel } from '../utils/replayMoment';
import { floatHover } from '../utils/shareFacts';
import { useWorkspace } from '../workspace';

interface Props {
  detail: TickerDetail;
  /** Replay company-fact note explaining why today's float/figures are omitted (#881). */
  replayNote?: string | null;
}

const ISO_DATE = /^(\d{4}-\d{2}-\d{2})/;

function resolveFloatTitle(detail: TickerDetail, replayNote?: string | null): string | undefined {
  const hover = floatHover(detail.fundamentals?.float_shares);
  if (hover) return hover;
  if (replayNote) return replayNote;
  if (detail.listing === null) {
    const stamp = detail.snapshot?.daily_bar?.timestamp ?? detail.snapshot?.latest_trade?.timestamp ?? '';
    const day = ISO_DATE.exec(stamp.trim())?.[1] ?? 'this session';
    return (
      `Replay of ${replayDayLabel(day)}: float, short interest, market cap, the 52-week range and broker `
      + "flags are not shown -- Nova holds today's figures only, not that day's."
    );
  }
  return undefined;
}

export function StockViewQuoteStats({ detail, replayNote = null }: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);
  const daily = detail.snapshot?.daily_bar;

  return (
    <div
      className="sv-quote-card__grid compact-grid sv-quote-stats"
      data-module="stock-view-quote"
      data-testid="stock-view-quote-stats"
    >
      <CompactGridCell
        label="Float"
        value={fmtVolume(detail.fundamentals?.float_shares)}
        title={resolveFloatTitle(detail, replayNote)}
      />
      <CompactGridCell label="Vol" value={fmtVolume(daily?.volume)} />
      <CompactGridCell
        label={QUOTE_RVOL_DAILY_LABEL}
        value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '--'}
        valueClass={
          detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH
            ? 'positive'
            : undefined
        }
        title={QUOTE_RVOL_DAILY_TITLE}
      />
      <CompactGridCell
        label="Gap%"
        value={m.gapPct != null ? `${(m.gapPct * 100).toFixed(2)}` : '--'}
        valueClass={pctToneClass(m.gapPct) || undefined}
        title={QUOTE_GAP_OPEN_TITLE}
      />
      <CompactGridCell label="High" value={fmtSessionPrice(daily?.high)} />
      <CompactGridCell label="Low" value={fmtSessionPrice(daily?.low)} />
    </div>
  );
}

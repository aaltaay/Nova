/** One scanner grid row. Memoized so a /ws/scanner price_patch only
 * reconciles the symbols that actually changed (D-031). */
import { memo, type ReactNode } from 'react';
import { SymbolSelectButton } from './SymbolSelectButton';
import { SelectableTableRow } from './SelectableTableRow';
import { ScannerPriceCell } from './ScannerPriceCell';
import { ScannerRowActions } from './ScannerRowActions';
import { ScannerRowMarks } from './ScannerRowMarks';
import { NewsCell } from './NewsCell';
import { EarningsDots } from './EarningsDots';
import { ScannerRowNumCell } from './ScannerTableChrome';
import { scannerColClass } from './scannerTableCol';
import { fmtMarketCap, fmtPct, fmtPrice, fmtVolume } from '../utils/quoteFormat';
import { SCANNER_CELL_ABSENT, SCANNER_CHANGE_CLOSE_TITLE } from '../constantGroups/scanner_board';
import { GapCell, fmtChangeAbs, pctClass, rvolSourceMark } from './ScannerRowCells';
import { SCANNER_QUOTE_CLOSE_FALLBACK } from '../scanner/scannerRowShape';
import type { ScannerRow } from '../types/scanner';
import type { WatchlistEntry } from '../strategy/types';

/** Compact Five Pillars checkmark + composite score. */
export function WatchCell({ watchlist }: { watchlist: WatchlistEntry | null | undefined }) {
  if (!watchlist) return <span className="na-muted">—</span>;
  const { five_pillars, composite_score } = watchlist;
  const failing = five_pillars.pillars.filter(p => !p.passed).map(p => p.name.replace('_', ' '));
  const title = `${five_pillars.pass_count}/${five_pillars.total} pillars pass` +
    (failing.length ? ` (failing: ${failing.join(', ')})` : ' — all pass') +
    ` · composite score ${composite_score.toFixed(0)}/100`;
  return (
    <span className="cell-stack" title={title}>
      <span className={`cell-stack-primary ${five_pillars.all_pass ? 'positive' : 'na-muted'}`}>
        {five_pillars.checkmark}
      </span>
      <span className="cell-stack-secondary">{composite_score.toFixed(0)} pts</span>
    </span>
  );
}

export type ScannerTableRowProps = {
  columns: [string, string][];
  row: ScannerRow;
  index: number;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  flash?: 'up' | 'down';
  stale: boolean;
  /** Largest |gap_percent| on the list -- the gap bar scales to the top row. Null: no bar. */
  gapScaleMax?: number | null;
};

/** True when this row can skip React reconciliation after a price_patch. */
export function scannerTableRowPropsEqual(
  prev: ScannerTableRowProps,
  next: ScannerTableRowProps,
): boolean {
  return (
    prev.row === next.row &&
    prev.index === next.index &&
    prev.selected === next.selected &&
    prev.flash === next.flash &&
    prev.stale === next.stale &&
    prev.columns === next.columns &&
    prev.onSelect === next.onSelect &&
    prev.onOpenTrading === next.onOpenTrading &&
    (prev.gapScaleMax ?? null) === (next.gapScaleMax ?? null)
  );
}

function renderCell(
  key: string,
  row: ScannerRow,
  flash: 'up' | 'down' | undefined,
  stale: boolean,
  gapScaleMax: number | null,
): ReactNode {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyRow = row as any;
  const closeFallback = row.quote_quality === SCANNER_QUOTE_CLOSE_FALLBACK;
  switch (key) {
    case 'symbol':
      return null;
    case 'price':
      return (
        <ScannerPriceCell
          symbol={row.symbol}
          price={row.price ?? anyRow.current_price}
          flash={flash}
          stale={stale}
          closeFallback={closeFallback}
        />
      );
    case 'prev_close':
      return fmtPrice(row.prev_close ?? anyRow.previous_close);
    case 'change_pct':
      // No trade yet: a change against the prior close would be invented (QA C50);
      // an unknown change is a muted dash, never a red N/A (QA V21).
      if (closeFallback || row.change_pct == null) {
        return (
          <span className="cell-stack" title={closeFallback ? SCANNER_CHANGE_CLOSE_TITLE : undefined}>
            <span className="cell-stack-primary na-muted">{SCANNER_CELL_ABSENT}</span>
            <span className="cell-stack-secondary">{closeFallback ? SCANNER_CELL_ABSENT : fmtChangeAbs(row.change_abs)}</span>
          </span>
        );
      }
      return (
        <span className="cell-stack">
          <span className={`cell-stack-primary ${row.change_pct >= 0 ? 'positive' : 'negative'}`}>
            {fmtPct(row.change_pct)}
          </span>
          <span className="cell-stack-secondary">{fmtChangeAbs(row.change_abs)}</span>
        </span>
      );
    case 'gap_percent':
      return <GapCell value={row.gap_percent} scaleMax={gapScaleMax} />;
    case 'volume': {
      const mark = rvolSourceMark(row.rvol_source);
      return (
        <span className="cell-stack cell-stack--volume" title={row.rel_volume != null ? mark.title : undefined}>
          <span className={`cell-stack-primary${row.volume == null ? ' na-muted' : ''}`}>{fmtVolume(row.volume)}</span>
          <span className="cell-stack-secondary">
            {row.rel_volume != null ? (
              <>
                {row.rel_volume}x
                <span className="rvol-source-badge" title={mark.title} data-rvol-source={row.rvol_source ?? 'unreported'}>
                  {mark.badge}
                </span>
              </>
            ) : (
              <span className="na-muted">{SCANNER_CELL_ABSENT}</span>
            )}
          </span>
        </span>
      );
    }
    case 'newest_headline_at':
      return <NewsCell newest_headline_at={row.newest_headline_at} />;
    case 'earnings_day_offset':
      return (
        <EarningsDots
          offset={row.earnings_day_offset}
          earningsDate={row.earnings_date}
          session={row.earnings_session}
          estimated={row.earnings_estimated}
        />
      );
    case 'watchlist_score':
      return <WatchCell watchlist={row.watchlist} />;
    case 'market_cap':
      return row.market_cap != null ? fmtMarketCap(row.market_cap) : <span className="na-muted">—</span>;
    case 'float':
      return row.float != null ? fmtVolume(row.float) : <span className="na-muted">—</span>;
    case 'short_interest':
      return (
        <span className="cell-stack">
          <span className="cell-stack-primary">
            {row.short_interest != null ? fmtVolume(row.short_interest) : <span className="na-muted">—</span>}
          </span>
          <span className="cell-stack-secondary">
            {row.short_ratio != null ? `${row.short_ratio.toFixed(1)}x ratio` : <span className="na-muted">{SCANNER_CELL_ABSENT}</span>}
          </span>
        </span>
      );
    case 'rvol':
      return row.rvol != null ? (
        <span className={row.rvol >= 2 ? 'positive' : ''}>{row.rvol.toFixed(1)}x</span>
      ) : <span className="na-muted">—</span>;
    case 'atr_expansion':
      return row.atr_expansion != null ? (
        <span className={row.atr_expansion >= 1 ? 'positive' : ''}>{row.atr_expansion.toFixed(1)}x</span>
      ) : <span className="na-muted">—</span>;
    case 'change_5d_pct':
      return <span className={pctClass(row.change_5d_pct)}>{fmtPct(row.change_5d_pct ?? null)}</span>;
    case 'change_20d_pct':
      return <span className={pctClass(row.change_20d_pct)}>{fmtPct(row.change_20d_pct ?? null)}</span>;
    case 'high_20d':
      return (
        <span className="cell-stack">
          <span className="cell-stack-primary">
            {row.high_20d != null ? fmtPrice(row.high_20d) : <span className="na-muted">—</span>}
          </span>
          <span className="cell-stack-secondary">
            {row.low_20d != null ? fmtPrice(row.low_20d) : <span className="na-muted">—</span>}
          </span>
        </span>
      );
    case 'large_cap_score':
      return row.large_cap_score != null ? (
        <span title={
          row.score_completeness != null
            ? `${Math.round(row.score_completeness * 100)}% of signals present`
            : undefined
        }>
          {row.large_cap_score.toFixed(0)}
        </span>
      ) : <span className="na-muted">—</span>;
    case 'days_to_earnings':
      return row.days_to_earnings != null ? (
        <span className={row.days_to_earnings <= 7 ? 'negative' : ''}>
          {row.days_to_earnings}d
        </span>
      ) : <span className="na-muted">—</span>;
    default:
      return <span className="na-muted">—</span>;
  }
}

function ScannerTableRowView({
  columns,
  row,
  index,
  selected,
  onSelect,
  onOpenTrading,
  flash,
  stale,
  gapScaleMax = null,
}: ScannerTableRowProps) {
  const last = columns.length - 1;
  return (
    <SelectableTableRow
      symbol={row.symbol}
      selected={selected}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
      openOnRowClick={false}
      botAllowlistMenu
      className="scanner-row"
    >
      <ScannerRowNumCell index={index} />
      {columns.map(([key], i) =>
        key === 'symbol' ? (
          <td key={key} data-col={key} className={scannerColClass(key)}>
            <span className="scanner-symbol-cell">
              <SymbolSelectButton
                symbol={row.symbol}
                exchange={row.exchange}
                selected={selected}
                onSelect={onSelect}
                onOpenTrading={onOpenTrading}
              />
              <ScannerRowMarks symbol={row.symbol} />
            </span>
          </td>
        ) : (
          <td
            key={key}
            data-col={key}
            className={`${scannerColClass(key)}${i === last ? ' scanner-row-actions-host' : ''}`}
          >
            {renderCell(key, row, flash, stale, gapScaleMax)}
            {/* The last cell hosts the hover actions so no column is added
                (the width roles are locked, #276). */}
            {i === last ? <ScannerRowActions symbol={row.symbol} onOpenTrading={onOpenTrading} /> : null}
          </td>
        )
      )}
    </SelectableTableRow>
  );
}

export const ScannerTableRow = memo(ScannerTableRowView, scannerTableRowPropsEqual);

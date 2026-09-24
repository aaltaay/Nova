/**
 * Middle top -- Performance: Account P&L | Symbol P&L | By source, with the
 * P&L / P&L % / Account value toggle re-rendering the big number and the
 * line. On Live the absence is stated; no curve is ever fabricated.
 */
import { useMemo } from 'react';
import {
  ACCOUNT_HISTORY_RANGES,
  ACCOUNT_PERF_EMPTY,
  ACCOUNT_PERF_LEGEND_BOT,
  ACCOUNT_PERF_LEGEND_EST,
  ACCOUNT_PERF_LEGEND_EST_NOTE,
  ACCOUNT_PERF_LEGEND_MANUAL,
  ACCOUNT_PERF_MODES,
  ACCOUNT_PERF_MODE_LABELS,
  ACCOUNT_PERF_ROW_COSTS,
  ACCOUNT_PERF_ROW_REALIZED,
  ACCOUNT_PERF_TAB_ACCOUNT,
  ACCOUNT_PERF_TAB_SOURCE,
  ACCOUNT_PERF_TAB_SYMBOL,
  ACCOUNT_PERF_TITLE,
  ACCOUNT_SOURCE_AUTO_PAPER_NOTE,
  ACCOUNT_SOURCE_FOOT,
  ACCOUNT_SOURCE_NO_FILLS,
  ACCOUNT_SOURCE_NO_FILLS_NOTE,
  ACCOUNT_SYMBOL_COL_COSTS,
  ACCOUNT_SYMBOL_COL_NET,
  ACCOUNT_SYMBOL_COL_OPEN,
  ACCOUNT_SYMBOL_COL_REALIZED,
  ACCOUNT_SYMBOL_COL_SYMBOL,
  ACCOUNT_SYMBOL_EMPTY,
  ACCOUNT_SYMBOL_FOOT,
  ACCOUNT_SYMBOL_TOTAL,
  accountPerfSubtitle,
  accountSourceFills,
  type AccountPerfMode,
  type AccountRange,
} from '../constantGroups/account_page';
import { formatSignedMoney, formatSignedPercent } from '../components/globalBarMoney';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { formatMoney } from '../utils/formatMoney';
import { EstChip, Money, PanelHead, Ring, etShortDate, toneClass, toneOf } from './accountBits';
import { isBotFill, rangeNetPnl, sourceCards, symbolPnlRows, type SymbolPnlRow } from './accountFigures';
import type { PracticeHistory } from './accountHistoryTypes';
import type { AccountPosition } from './accountPositions';
import { EquityCurve, type CurveMarker } from './EquityCurve';
import { rangeSeries, tickDecimals } from './equityPath';

export type PerfTab = 'account' | 'symbol' | 'source';

interface Props {
  history: PracticeHistory | null;
  /** Stated absence (Live, nothing loaded, not answered yet); null when history renders. */
  absence: string | null;
  positions: AccountPosition[];
  range: AccountRange;
  onRange: (range: AccountRange) => void;
  mode: AccountPerfMode;
  onMode: (mode: AccountPerfMode) => void;
  tab: PerfTab;
  onTab: (tab: PerfTab) => void;
  nowTs: number;
  /** Total account value, for the P&L % base and the value curve's live end. */
  netLiquidation: number | null;
  /** The account's open P&L at the live mark -- the headline's "open" (QA W1). */
  openPnl: number | null;
}

const TABS: Array<[PerfTab, string]> = [
  ['account', ACCOUNT_PERF_TAB_ACCOUNT],
  ['symbol', ACCOUNT_PERF_TAB_SYMBOL],
  ['source', ACCOUNT_PERF_TAB_SOURCE],
];

/**
 * P&L % against the value the range started from. Null until the account has
 * loaded: a missing net liquidation is not zero, and treating it as zero read
 * as "-100.00%" for any loss (C47).
 */
export function rangePnlPercent(net: number | null, netLiquidation: number | null): number | null {
  if (net == null || netLiquidation == null || !Number.isFinite(netLiquidation)) return null;
  const base = netLiquidation - net;
  return base > 0 ? (net / base) * 100 : null;
}

function bigNumber(net: number | null, mode: AccountPerfMode, netLiquidation: number | null): string {
  if (mode === 'value') return formatMoney(netLiquidation);
  if (mode === 'pct') return formatSignedPercent(rangePnlPercent(net, netLiquidation));
  return formatSignedMoney(net);
}

/** Axis labels: whole dollars / tenths of a percent, cents when the ticks are closer (W13 / W26). */
export function perfTick(mode: AccountPerfMode, value: number, step: number): string {
  if (mode === 'pct') return `${value.toFixed(tickDecimals(step, 'pct'))}%`;
  const d = tickDecimals(step, 'money');
  if (mode === 'value') return value.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  return formatSignedMoney(value, d);
}

/** The curve's end tag: the headline's own precision, never rounded to a dollar (W13). */
function perfLastLabel(mode: AccountPerfMode, value: number): string {
  if (mode === 'pct') return formatSignedPercent(value);
  if (mode === 'value') return formatMoney(value);
  return formatSignedMoney(value);
}

export function PerformancePanel({
  history, absence, positions, range, onRange, mode, onMode, tab, onTab, nowTs, netLiquidation, openPnl,
}: Props) {
  const net = history ? rangeNetPnl(history.components, openPnl) : null;
  const { series, baseline } = history
    ? rangeSeries(history, mode, { openPnl, netLiquidation }, nowTs)
    : { series: [], baseline: 0 };
  const markers: CurveMarker[] = history
    ? history.fills.map((f) => ({
        ts: f.ts,
        tone: isBotFill(f) ? 'bot' : 'manual',
        title: `${f.side} ${f.qty} ${f.symbol} @ ${f.price} · ${f.source ?? '—'}${f.bot_id ? ` ${f.bot_id}` : ''}`,
      }))
    : [];
  const resetLabel = history?.archives.length
    ? etShortDate(history.archives[history.archives.length - 1].closed_at)
    : null;
  const botIds = history ? [...new Set(history.fills.filter(isBotFill).map((f) => f.bot_id).filter(Boolean))] : [];
  const formatTick = (v: number, step: number): string => perfTick(mode, v, step);

  return (
    <section className="acct-panel acct-panel--perf" data-testid="account-performance" aria-label={ACCOUNT_PERF_TITLE}>
      <PanelHead
        title={ACCOUNT_PERF_TITLE}
        tabs={
          <div className="acct-ptabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} className={`acct-ptabs__item${tab === id ? ' is-on' : ''}`} data-testid={`account-perf-tab-${id}`} onClick={() => onTab(id)}>
                {label}
              </button>
            ))}
          </div>
        }
      >
        <div className="acct-seg" role="group">
          {ACCOUNT_PERF_MODES.map((m) => (
            <button key={m} type="button" aria-pressed={mode === m} className={`acct-seg__item${mode === m ? ' is-on' : ''}`} data-testid={`account-perf-mode-${m}`} onClick={() => onMode(m)}>
              {ACCOUNT_PERF_MODE_LABELS[m]}
            </button>
          ))}
        </div>
      </PanelHead>

      {!history ? (
        <div className="acct-absent" data-testid="account-performance-absent">{absence}</div>
      ) : (
        <>
          <div className="acct-perf__top">
            <span className={`acct-hero__big acct-num ${mode === 'value' ? '' : toneClass(toneOf(net))}`} data-testid="account-perf-big">
              {bigNumber(net, mode, netLiquidation)}
            </span>
            <span className="acct-muted">{accountPerfSubtitle(range, etShortDate(history.ledger_opened_at))}</span>
            <div className="acct-ranges acct-ranges--right" role="tablist">
              {ACCOUNT_HISTORY_RANGES.map((r) => (
                <button key={r} type="button" role="tab" aria-selected={range === r} className={`acct-ranges__item${range === r ? ' is-on' : ''}`} data-testid={`account-perf-range-${r}`} onClick={() => onRange(r)}>
                  {r}
                </button>
              ))}
            </div>
          </div>

          {tab === 'account' && (
            series.length ? (
              <>
                <EquityCurve series={series} baseline={baseline} endTs={nowTs} formatTick={formatTick} lastLabel={series.length ? perfLastLabel(mode, series[series.length - 1].value) : null} markers={markers} height={150} padLeft={56} testId="account-perf-curve" />
                <div className="acct-clegend">
                  <span><i className="acct-sw is-accent" />{ACCOUNT_PERF_LEGEND_MANUAL}</span>
                  <span><i className="acct-sw is-bot" />{ACCOUNT_PERF_LEGEND_BOT}{botIds.length ? ` · ${botIds.join(', ')}` : ''}</span>
                  <span>{ACCOUNT_PERF_LEGEND_EST} <EstChip /> {ACCOUNT_PERF_LEGEND_EST_NOTE}</span>
                </div>
              </>
            ) : (
              <div className="acct-absent acct-absent--curve" data-testid="account-perf-empty">{ACCOUNT_PERF_EMPTY}</div>
            )
          )}

          {tab === 'symbol' && <SymbolTable history={history} positions={positions} />}
          {tab === 'source' && <SourceTiles history={history} />}

          <div className="acct-rows acct-rows--perf">
            <div className="acct-row"><span className="acct-row__k" data-testid="account-perf-realized-label">{ACCOUNT_PERF_ROW_REALIZED(range, resetLabel)}</span><span className="acct-row__v"><Money value={history.components.realized} signed /></span></div>
            <div className="acct-row"><span className="acct-row__k">{ACCOUNT_PERF_ROW_COSTS}</span><span className="acct-row__v"><Money value={-(history.components.commissions + history.components.sec_finra_fees)} signed={history.components.commissions + history.components.sec_finra_fees !== 0} kind="cost" /></span></div>
          </div>
        </>
      )}
    </section>
  );
}

const SYMBOL_COLUMNS: SortColumns<SymbolPnlRow> = {
  symbol: (r) => r.symbol,
  realized: (r) => r.realized,
  open: (r) => r.open,
  // The cell shows costs as a debit (-$1.20), so they sort on that signed figure.
  costs: (r) => -r.costs,
  net: (r) => r.net,
};

function SymbolTable({ history, positions }: { history: PracticeHistory; positions: AccountPosition[] }) {
  const { rows, total } = useMemo(
    () => symbolPnlRows(history.fills, positions.map((p) => ({ symbol: p.symbol, unrealized: p.unrealized }))),
    [history.fills, positions],
  );
  // The Total row stays last whatever the sort.
  const { rows: sorted, sort, onSort } = useTableSort('account.symbol-pnl', rows, SYMBOL_COLUMNS);
  if (!rows.length) return <div className="acct-absent" data-testid="account-symbol-empty">{ACCOUNT_SYMBOL_EMPTY}</div>;
  return (
    <div className="acct-scroll">
      <table className="acct-table" data-testid="account-symbol-table">
        <thead>
          <tr>
            <SortTh col="symbol" sort={sort} onSort={onSort}>{ACCOUNT_SYMBOL_COL_SYMBOL}</SortTh>
            <SortTh col="realized" sort={sort} onSort={onSort} className="r">{ACCOUNT_SYMBOL_COL_REALIZED}</SortTh>
            <SortTh col="open" sort={sort} onSort={onSort} className="r">{ACCOUNT_SYMBOL_COL_OPEN}</SortTh>
            <SortTh col="costs" sort={sort} onSort={onSort} className="r">{ACCOUNT_SYMBOL_COL_COSTS}</SortTh>
            <SortTh col="net" sort={sort} onSort={onSort} className="r">{ACCOUNT_SYMBOL_COL_NET}</SortTh>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.symbol} data-testid={`account-symbol-row-${row.symbol}`}>
              <td>{row.symbol}</td>
              <td className="r"><Money value={row.realized} signed /></td>
              <td className="r">{row.open == null ? <span className="acct-muted">—</span> : <Money value={row.open} signed />}</td>
              <td className="r"><Money value={-row.costs} signed={row.costs !== 0} kind="cost" /></td>
              <td className="r"><Money value={row.net} signed /></td>
            </tr>
          ))}
          <tr className="acct-table__total">
            <td>{ACCOUNT_SYMBOL_TOTAL}</td>
            <td className="r"><Money value={total.realized} signed /></td>
            <td className="r">{total.open == null ? <span className="acct-muted">—</span> : <Money value={total.open} signed />}</td>
            <td className="r"><Money value={-total.costs} signed={total.costs !== 0} kind="cost" /></td>
            <td className="r"><Money value={total.net} signed /></td>
          </tr>
        </tbody>
      </table>
      <p className="acct-foot">{ACCOUNT_SYMBOL_FOOT}</p>
    </div>
  );
}

function SourceTiles({ history }: { history: PracticeHistory }) {
  const cards = sourceCards(history.by_source);
  return (
    <div className="acct-scroll">
      <div className="acct-srcs" data-testid="account-source-tiles">
        {cards.map((card) => (
          <div key={`${card.kind}-${card.botId ?? ''}`} className="acct-src" data-testid={`account-source-${card.kind}`}>
            <Ring share={card.share} tone={card.kind === 'bot' ? 'bot' : card.fills ? 'up' : 'muted'} size={64} />
            <div>
              <div className="acct-src__k">{card.label}</div>
              {card.net == null
                ? <div className="acct-src__v acct-muted">{ACCOUNT_SOURCE_NO_FILLS}</div>
                : <div className={`acct-src__v acct-num ${toneClass(toneOf(card.net))}`}>{formatSignedMoney(card.net)}</div>}
              <div className="acct-src__s">
                {card.fills
                  ? `${accountSourceFills(card.fills)} · comm ${formatMoney(-card.commissions)} · fees ${formatMoney(-card.fees)}`
                  : card.kind === 'auto_paper' ? ACCOUNT_SOURCE_AUTO_PAPER_NOTE : ACCOUNT_SOURCE_NO_FILLS_NOTE}
                {!card.fills && card.kind === 'auto_paper' && <><br />{ACCOUNT_SOURCE_NO_FILLS_NOTE}</>}
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="acct-foot">{ACCOUNT_SOURCE_FOOT}</p>
    </div>
  );
}

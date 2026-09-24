/** What one setup's armed setups did (ADR 022, ADR 031). Every armed setup is
 * scored the way the backtest scored its own trades, so live and research numbers
 * compare. These are scores, not fills: nothing here was traded. */
import {
  SETUPS_DAYS_LABELS,
  SETUPS_SCOREBOARD_DAYS,
  SETUPS_SPLIT_KEY_LABELS,
  SETUPS_SPLIT_TITLES,
} from '../constants';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { fmtPct, fmtR } from './setupsFormat';
import { setupLabel } from './setupWords';
import type { ScoreStats, Scoreboard } from './types';

interface Props {
  data: Scoreboard | null;
  error: string | null;
  loading: boolean;
  days: number;
  onDays: (days: number) => void;
  /** The setup the scoreboard answers for (the board's filter, else the chosen setup). */
  setup?: string;
}

/** One group row of a split (the tape said go, grade A, premarket, ...). */
interface SplitEntry {
  split: string;
  key: string;
  stats: ScoreStats;
}

/** A header sorts the groups inside each split; the splits and the all-setups row stay put. */
const COLUMNS: SortColumns<SplitEntry> = {
  armed: e => e.stats.armed,
  triggered: e => e.stats.triggered,
  target_first: e => e.stats.target_first,
  stop_first: e => e.stats.stop_first,
  open: e => e.stats.open,
  win: e => e.stats.win_pct,
  avg_r: e => e.stats.avg_r,
  net_r: e => e.stats.avg_net_r,
  mfe: e => e.stats.avg_mfe_r,
  mae: e => e.stats.avg_mae_r,
};

/** Every split's groups in reading order (go before wait before blind), anything new after them. */
function splitEntries(data: Scoreboard | null, splits: readonly string[]): SplitEntry[] {
  if (!data) return [];
  return splits.flatMap(split => {
    const order = Object.keys(SETUPS_SPLIT_KEY_LABELS[split] ?? {});
    const rank = (key: string) => (order.includes(key) ? order.indexOf(key) : order.length);
    return Object.entries(data.summary.by[split])
      .sort(([a], [b]) => rank(a) - rank(b))
      .map(([key, stats]) => ({ split, key, stats }));
  });
}

function StatCells({ s }: { s: ScoreStats }) {
  const rate = s.trigger_rate != null ? ` (${fmtPct(s.trigger_rate * 100)})` : '';
  return (
    <>
      <td className="num">{s.armed}</td>
      <td className="num">{s.triggered}{rate}</td>
      <td className="num">{s.target_first}</td>
      <td className="num">{s.stop_first}</td>
      <td className="num">{s.open}</td>
      <td className="num">{fmtPct(s.win_pct)}</td>
      <td className="num">{fmtR(s.avg_r)}</td>
      <td className="num">{fmtR(s.avg_net_r)}</td>
      <td className="num">{fmtR(s.avg_mfe_r)}</td>
      <td className="num">{fmtR(s.avg_mae_r)}</td>
    </>
  );
}

export function SetupsScoreboard({ data, error, loading, days, onDays, setup }: Props) {
  const splits = data ? Object.keys(SETUPS_SPLIT_TITLES).filter(k => data.summary.by[k]) : [];
  const entries = splitEntries(data, splits);
  const { rows: sorted, sort, onSort } = useTableSort('setups.scoreboard', entries, COLUMNS);
  return (
    <div className="setups-scoreboard">
      <div className="setups-toolbar">
        <b data-testid="setups-scoreboard-setup">{setupLabel(data?.setup_type ?? setup ?? 'first_pullback')}</b>
        <span className="na-muted">Range</span>
        {SETUPS_SCOREBOARD_DAYS.map(d => (
          <button
            key={d}
            type="button"
            className={`sub-tab ${days === d ? 'active' : ''}`}
            onClick={() => onDays(d)}
          >
            {SETUPS_DAYS_LABELS[d] ?? `${d} days`}
          </button>
        ))}
        {data ? (
          <span className="na-muted">
            {data.row_count} armed{data.date_from ? ` since ${data.date_from}` : ''}
          </span>
        ) : null}
      </div>
      <p className="setups-note">
        Each armed setup is scored the way the backtest scored its trades: whether the target or the
        stop came first, and what the exit rules made of it in R. Net R takes 1¢ a fill off. These are
        scores on live one-minute bars, not fills. The row to watch is &ldquo;Tape said go&rdquo; against
        the others.
      </p>
      {error && <div className="empty-state">{error}</div>}
      {!error && !data && <div className="empty-state">{loading ? 'Loading the scoreboard\u2026' : 'No scoreboard yet.'}</div>}
      {data && (
        <div className="table-wrapper setups-table">
          <table>
            <thead>
              <tr>
                <th />
                <SortTh col="armed" sort={sort} onSort={onSort} title="Setups that armed: a leg, a pullback and a known trigger and stop">Armed</SortTh>
                <SortTh col="triggered" sort={sort} onSort={onSort} title="Price traded over the trigger (and the share that did)">Triggered</SortTh>
                <SortTh col="target_first" sort={sort} onSort={onSort} title="Target 1 traded before the stop">Target first</SortTh>
                <SortTh col="stop_first" sort={sort} onSort={onSort} title="The stop traded before target 1">Stop first</SortTh>
                <SortTh col="open" sort={sort} onSort={onSort} title="Triggered, neither level reached yet">Open</SortTh>
                <SortTh col="win" sort={sort} onSort={onSort} title="Share of scored setups the exit rules closed above zero">Win</SortTh>
                <SortTh col="avg_r" sort={sort} onSort={onSort} title="Average R under the backtest's exit rules, before costs">Avg R</SortTh>
                <SortTh col="net_r" sort={sort} onSort={onSort} title="Average R after 1¢ a fill">Net R</SortTh>
                <SortTh col="mfe" sort={sort} onSort={onSort} title="Average best move in the first 15 minutes, in R">MFE</SortTh>
                <SortTh col="mae" sort={sort} onSort={onSort} title="Average worst move in the first 15 minutes, in R">MAE</SortTh>
              </tr>
            </thead>
            <tbody>
              <tr className="setups-split-total">
                <th scope="row">All armed setups</th>
                <StatCells s={data.summary.all} />
              </tr>
              {splits.map(split => (
                <SplitRows key={split} split={split} entries={sorted.filter(e => e.split === split)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SplitRows({ split, entries }: { split: string; entries: readonly SplitEntry[] }) {
  const labels = SETUPS_SPLIT_KEY_LABELS[split] ?? {};
  return (
    <>
      <tr className="setups-split-head">
        <th colSpan={11}>{SETUPS_SPLIT_TITLES[split] ?? split}</th>
      </tr>
      {entries.map(({ key, stats }) => (
        <tr key={`${split}-${key}`}>
          <th scope="row">{labels[key] ?? key}</th>
          <StatCells s={stats} />
        </tr>
      ))}
    </>
  );
}

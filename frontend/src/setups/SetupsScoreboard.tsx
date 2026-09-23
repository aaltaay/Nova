/** What the armed setups did (ADR 022). Every armed setup is scored the way the
 * backtest scored its own trades, so live and research numbers compare. These
 * are scores, not fills: nothing here was traded. */
import {
  SETUPS_DAYS_LABELS,
  SETUPS_SCOREBOARD_DAYS,
  SETUPS_SPLIT_KEY_LABELS,
  SETUPS_SPLIT_TITLES,
} from '../constants';
import { fmtPct, fmtR } from './setupsFormat';
import type { ScoreStats, Scoreboard } from './types';

interface Props {
  data: Scoreboard | null;
  error: string | null;
  loading: boolean;
  days: number;
  onDays: (days: number) => void;
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

export function SetupsScoreboard({ data, error, loading, days, onDays }: Props) {
  const splits = data ? Object.keys(SETUPS_SPLIT_TITLES).filter(k => data.summary.by[k]) : [];
  return (
    <div className="setups-scoreboard">
      <div className="setups-toolbar">
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
                <th title="Setups that armed: a leg, a pullback and a known trigger and stop">Armed</th>
                <th title="Price traded over the trigger (and the share that did)">Triggered</th>
                <th title="Target 1 traded before the stop">Target first</th>
                <th title="The stop traded before target 1">Stop first</th>
                <th title="Triggered, neither level reached yet">Open</th>
                <th title="Share of scored setups the exit rules closed above zero">Win</th>
                <th title="Average R under the backtest's exit rules, before costs">Avg R</th>
                <th title="Average R after 1¢ a fill">Net R</th>
                <th title="Average best move in the first 15 minutes, in R">MFE</th>
                <th title="Average worst move in the first 15 minutes, in R">MAE</th>
              </tr>
            </thead>
            <tbody>
              <tr className="setups-split-total">
                <th scope="row">All armed setups</th>
                <StatCells s={data.summary.all} />
              </tr>
              {splits.map(split => (
                <SplitRows key={split} split={split} groups={data.summary.by[split]} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SplitRows({ split, groups }: { split: string; groups: Record<string, ScoreStats> }) {
  const labels = SETUPS_SPLIT_KEY_LABELS[split] ?? {};
  return (
    <>
      <tr className="setups-split-head">
        <th colSpan={11}>{SETUPS_SPLIT_TITLES[split] ?? split}</th>
      </tr>
      {Object.entries(groups).map(([key, s]) => (
        <tr key={`${split}-${key}`}>
          <th scope="row">{labels[key] ?? key}</th>
          <StatCells s={s} />
        </tr>
      ))}
    </>
  );
}

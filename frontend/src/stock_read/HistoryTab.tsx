/** The sheet's History tab: the stored daily bars with every +40% run marked, the runs themselves, and
 * what Nova holds on the symbol -- with what it does not keep per symbol yet said so. */
import { dayShort } from './timeWords';
import { fmtPx } from './planMath';
import { ReadRowList } from './ReadRows';
import type { DailyBar, RunDay, StockHistory } from './types';
import type { PolledState } from './useStockRead';

const W = 600;
const H = 170;
const PAD_R = 34;
const PAD_B = 16;
const PAD_T = 10;

function pct(x: number): string {
  return `${x >= 0 ? '+' : ''}${Math.round(x * 100)}%`;
}

export function historySummary(h: StockHistory): string {
  const past = h.runs.filter(r => !r.today);
  const today = h.runs.find(r => r.today);
  const bits: string[] = [];
  bits.push(past.length === 0
    ? `${h.symbol} has no +40% run in its stored daily bars.`
    : `${h.symbol} ran +40% or more on ${past.length} day${past.length === 1 ? '' : 's'} in its stored daily bars.`);
  if (past.length) {
    const faded = past.slice(0, 3).filter(r => r.close < r.high * 0.8).length;
    const last = past[0];
    bits.push(`The last, ${dayShort(last.date)}: high ${pct(last.run_pct)}, closed ${pct(last.close_pct)}.`);
    if (past.length >= 2) bits.push(`${faded} of the last ${Math.min(3, past.length)} gave back over a fifth of the high by the close.`);
  }
  if (today) bits.push(`Today so far: high ${pct(today.run_pct)} over the prior close.`);
  const s = h.split;
  const parts = s?.factor ? /^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/.exec(s.factor) : null;
  if (s && parts && s.days_ago !== null) {
    bits.push(`A ${parts[1]}-for-${parts[2]} ${s.reverse ? 'reverse ' : ''}split ${Math.round(s.days_ago)} days ago.`);
  }
  return bits.join(' ');
}

export function DailyRunsChart({ daily, runs }: { daily: DailyBar[]; runs: RunDay[] }) {
  if (daily.length < 2) return <p className="sr-empty">No stored daily bars for it.</p>;
  const hi = Math.max(...daily.map(b => b.h));
  const lo = Math.min(...daily.map(b => b.l));
  const span = hi - lo || hi || 1;
  const plotW = W - PAD_R;
  const step = plotW / daily.length;
  const y = (p: number) => PAD_T + (1 - (p - lo) / span) * (H - PAD_T - PAD_B);
  const runDays = new Map(runs.map(r => [r.date, r]));
  const ticks = [hi, lo + span / 2, lo];
  const labelEvery = Math.max(1, Math.ceil(daily.length / 5));
  return (
    <svg className="sr-daily" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily bars with runs of +40% marked"
      data-testid="stock-read-daily-chart">
      {ticks.map(t => (
        <g key={t}>
          <line x1={0} x2={plotW} y1={y(t)} y2={y(t)} className="sr-daily__grid" />
          <text x={W - 2} y={y(t) + 3} className="sr-daily__axis" textAnchor="end">{fmtPx(t)}</text>
        </g>
      ))}
      {daily.map((b, i) => {
        const x = i * step + step / 2;
        const up = b.c >= b.o;
        const top = y(Math.max(b.o, b.c));
        const bodyH = Math.max(1, Math.abs(y(b.o) - y(b.c)));
        const run = runDays.get(b.d);
        return (
          <g key={b.d} className={up ? 'sr-daily__up' : 'sr-daily__down'}>
            <line x1={x} x2={x} y1={y(b.h)} y2={y(b.l)} />
            <rect x={x - Math.max(0.6, step * 0.35)} width={Math.max(1.2, step * 0.7)} y={top} height={bodyH} />
            {run && (
              <g className={`sr-daily__run${run.today ? ' sr-daily__run--today' : ''}`}>
                <path d={`M${x} ${y(b.h) - 11} l4 4 l-4 4 l-4 -4 z`} />
                <title>{`${dayShort(b.d)}: high ${fmtPx(run.high)}, ${pct(run.run_pct)} over ${fmtPx(run.prior_close)}; closed ${pct(run.close_pct)}`}</title>
              </g>
            )}
            {i % labelEvery === 0 && (
              <text x={x} y={H - 3} className="sr-daily__axis" textAnchor="middle">{dayShort(b.d)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function HistoryTab({ state }: { state: PolledState<StockHistory> }) {
  const h = state.data;
  if (!h) {
    return (
      <div className="sr-tab" data-testid="stock-read-history">
        <p className="sr-empty">{state.error ?? (state.unavailable ? 'This backend has no history read yet: reload it.' : 'Reading the history…')}</p>
      </div>
    );
  }
  return (
    <div className="sr-tab sr-tab--history" data-testid="stock-read-history">
      <p className="sr-summary">{historySummary(h)}</p>
      <h4 className="sr-subhead">Daily, the last {h.daily.length} sessions (IBKR daily bars)</h4>
      <DailyRunsChart daily={h.daily} runs={h.runs} />
      <h4 className="sr-subhead">Runs of +40% intraday</h4>
      {h.runs.length === 0 ? (
        <p className="sr-empty">None in the stored daily bars.</p>
      ) : (
        <table className="sr-runs" data-testid="stock-read-runs">
          <thead>
            <tr><th>Day</th><th>Prior close</th><th>High</th><th>Close</th><th>Run</th><th>Close vs prior</th></tr>
          </thead>
          <tbody>
            {h.runs.map(r => (
              <tr key={r.date} className={r.today ? 'sr-runs__today' : undefined}>
                <td>{dayShort(r.date)}{r.today ? ' (today)' : ''}</td>
                <td>{fmtPx(r.prior_close)}</td>
                <td>{fmtPx(r.high)}</td>
                <td>{fmtPx(r.close)}</td>
                <td className="sr-pos">{pct(r.run_pct)}</td>
                <td className={r.close_pct >= 0 ? 'sr-pos' : 'sr-neg'}>{pct(r.close_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="sr-note">Daily bars close on the day&apos;s last extended-hours trade, not the 16:00 close.</p>
      <h4 className="sr-subhead">What Nova holds on {h.symbol}</h4>
      <ReadRowList rows={h.holdings} />
    </div>
  );
}

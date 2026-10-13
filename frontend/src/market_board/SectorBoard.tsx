/** The sector and industry boards (ADR 053): strongest first, a green / red bar, the period's leader. */
import { BAR_SCALE_PCT, PERIOD_LABEL } from './constants';
import { shortDate, signedPct, tone } from './format';
import { Card, PeriodSwitch, Sym } from './parts';
import type { Period, SectorBoard } from './types';

function span(board: SectorBoard): string {
  return board.period === '1D' ? 'today' : `${shortDate(board.from)} – ${shortDate(board.to)}`;
}

export function SectorBoardCard({ kind, board, onPeriod, onOpen }: {
  kind: 'sectors' | 'industries';
  board: SectorBoard;
  onPeriod: (p: Period) => void;
  onOpen?: (symbol: string) => void;
}) {
  const scale = BAR_SCALE_PCT[board.period];
  const title = kind === 'sectors' ? 'Sectors' : 'Industries & themes';
  const hint = `${span(board)} · ${kind === 'sectors' ? "the S&P's 11" : 'where small caps run'}, strongest first`;
  return (
    <Card title={title} hint={hint} className="mk-board" testId={`market-${kind}`}
      extra={<PeriodSwitch value={board.period} onChange={onPeriod} label={`${title} period`} />}>
      <div className="mk-board__colh">
        <span>{kind === 'sectors' ? 'Sector' : 'Industry'}</span><span>ETF</span>
        <span className="mk-c" title={`The bar runs from -${scale}% to +${scale}%`}>&plusmn;{scale}%</span>
        <span className="mk-r">{PERIOD_LABEL[board.period]}</span>
        <span className="mk-r">{PERIOD_LABEL[board.rows[0]?.context_period ?? '7D']}</span>
        <span>{board.period === '1D' ? 'Leader' : "Period's leader"}</span>
      </div>
      {board.rows.map((r) => {
        const w = r.change_pct == null ? 0 : Math.min(Math.abs(r.change_pct) / scale, 1) * 50;
        return (
          <div key={r.etf} className="mk-board__row">
            <span className="mk-b">{r.name}</span>
            <span className="mk-muted">{r.etf}</span>
            <span className="mk-bar" aria-hidden="true">
              {r.change_pct == null ? null : (
                <i className={r.change_pct >= 0 ? 'is-up' : 'is-down'}
                  style={r.change_pct >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }} />
              )}
            </span>
            <span className={`mk-r mk-b is-${tone(r.change_pct)}`}>{signedPct(r.change_pct)}</span>
            <span className={`mk-r mk-small is-${tone(r.context_pct)}`}>{signedPct(r.context_pct)}</span>
            <span className="mk-chip">
              {r.leader ? (
                <><Sym symbol={r.leader.symbol} onOpen={onOpen} /> <em className={`is-${tone(r.leader.change_pct)}`}>{signedPct(r.leader.change_pct, 1)}</em></>
              ) : (
                <span className="mk-muted" title={r.leader_why ?? undefined}>
                  {'—'} {r.leader_why === 'none in the movers' ? r.leader_why : ''}
                </span>
              )}
            </span>
          </div>
        );
      })}
      {kind === 'sectors' ? <Rotation board={board} /> : null}
    </Card>
  );
}

function Rotation({ board }: { board: SectorBoard }) {
  const off = board.offense_pct ?? null;
  const def = board.defense_pct ?? null;
  const lean = off == null || def == null ? null : off > def ? 'into offense' : off < def ? 'into defense' : null;
  return (
    <>
      <div className="mk-rot">
        <div className="mk-box"><div className="mk-t">Offense · tech, discretionary, comms</div>
          <div className={`mk-v is-${tone(off)}`}>{signedPct(off)} <span className="mk-small mk-muted">avg</span></div></div>
        <div className="mk-box"><div className="mk-t">Defense · staples, utilities, health</div>
          <div className={`mk-v is-${tone(def)}`}>{signedPct(def)} <span className="mk-small mk-muted">avg</span></div></div>
      </div>
      <p className="mk-small mk-muted mk-rot__note">
        {lean ? <>Money is leaning <b className={lean === 'into offense' ? 'is-up' : 'is-down'}>{lean}</b> — {lean === 'into offense' ? 'a risk-on read' : 'a risk-off read'}.</> : 'Offense and defense are level, or not quoted yet.'}
      </p>
    </>
  );
}

/** The Global page's top strip (ADR 060): the day's read, the world, and each region -- pressure and index moves. */
import { VERDICT_TONE } from './constants';
import { signedPct, tone, usd } from './format';
import type { Read, Region, Totals } from './types';

function Money({ t }: { t: Totals }) {
  return (
    <div className="gb-kpi__pair">
      <div>
        <small>Pressure</small>
        <b className={`is-${tone(t.pressure_usd)}`}>{usd(t.pressure_usd, true)}</b>
      </div>
      <div>
        <small>Avg move</small>
        <b className={`is-${tone(t.avg_move_pct)}`}>{signedPct(t.avg_move_pct, 2)}</b>
      </div>
    </div>
  );
}

function Sub({ t }: { t: Totals }) {
  return (
    <span className="gb-kpi__n">
      {t.pressure_pct != null ? `${signedPct(t.pressure_pct)} of ${usd(t.traded_usd)} traded` : 'no money read yet'}
      <br />
      {`${t.up} of ${t.markets} up · ${t.down} down`}
    </span>
  );
}

export function KpiStrip({ read, world, regions }: { read: Read; world: Totals; regions: Region[] }) {
  const verdictTone = read.verdict ? VERDICT_TONE[read.verdict] : 'flat';
  return (
    <div className="gb-kpis" data-testid="global-kpis">
      <div className={`gb-kpi gb-kpi--read is-${verdictTone}`} title={read.rule} data-testid="global-read">
        <span className="gb-kpi__t">Today's read</span>
        <b className="gb-kpi__headline">{read.headline}</b>
        <span className="gb-kpi__n">{read.detail}</span>
      </div>
      <div className="gb-kpi" data-testid="global-world">
        <span className="gb-kpi__t">World</span>
        <Money t={world} />
        <Sub t={world} />
      </div>
      {regions.map((r) => (
        <div key={r.id} className="gb-kpi" data-testid={`global-region-${r.id}`}>
          <span className="gb-kpi__t">{r.label}</span>
          <Money t={r} />
          <Sub t={r} />
        </div>
      ))}
    </div>
  );
}

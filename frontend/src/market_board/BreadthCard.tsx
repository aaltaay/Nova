/** NYSE breadth (ADR 053): how many stocks join the move; before 09:30 the last session's close, labelled. */
import { count, etTime, signedNum } from './format';
import { Card, Spark } from './parts';
import type { Breadth, BreadthNumbers } from './types';

function Split({ label, a, b, right }: { label: string; a: number | null; b: number | null; right: string }) {
  const total = (a ?? 0) + (b ?? 0);
  const pa = total ? ((a ?? 0) / total) * 100 : 50;
  return (
    <div className="mk-brow">
      <span>{label}</span>
      <span className="mk-ad" aria-hidden="true"><i className="is-up" style={{ width: `${pa}%` }} /><i className="is-down" style={{ width: `${100 - pa}%` }} /></span>
      <span className="mk-r">{right}</span>
    </div>
  );
}

function Numbers({ n, faded }: { n: BreadthNumbers; faded: boolean }) {
  const vol = n.up_volume != null && n.down_volume != null && n.up_volume + n.down_volume > 0
    ? Math.round((100 * n.up_volume) / (n.up_volume + n.down_volume)) : null;
  return (
    <div className={faded ? 'mk-faded' : ''}>
      <Split label="Up / down stocks" a={n.advancing} b={n.declining} right={`${count(n.advancing)} / ${count(n.declining)}`} />
      <Split label="Up / down volume" a={n.up_volume} b={n.down_volume} right={vol == null ? '--' : `${vol}% up volume`} />
    </div>
  );
}

export function BreadthCard({ breadth }: { breadth: Breadth }) {
  const waiting = breadth.state === 'waiting';
  const shown: BreadthNumbers = waiting && breadth.prior ? breadth.prior : breadth;
  return (
    <Card title="Breadth · NYSE" hint="how many stocks join the move" className="mk-breadth" testId="market-breadth"
      extra={<span className="mk-src mk-push">IBKR AD-NYSE · VOL-NYSE · TICK-NYSE · TRIN-NYSE</span>}>
      {breadth.state !== 'ok' ? (
        <p className="mk-wait" role="status">
          {breadth.why}{waiting && breadth.prior ? <> Shown below: <b>{breadth.prior.date}&apos;s last sample</b>, for context.</> : null}
        </p>
      ) : null}
      {breadth.state === 'unavailable' && !breadth.prior ? null : <Numbers n={shown} faded={waiting} />}
      <div className="mk-kv">
        <div className="mk-box mk-box--wide">
          <div className="mk-t">Up minus down stocks{breadth.line_since ? `, since ${etTime(breadth.line_since)}` : ''}</div>
          <Spark points={breadth.ad_line} height={28} zero={0} label="NYSE advancing minus declining" />
        </div>
        <div className={`mk-box${waiting ? ' mk-faded' : ''}`}><div className="mk-t">TICK</div>
          <div className="mk-v">{signedNum(shown.tick, 0)}</div><div className="mk-s">upticks − downticks</div></div>
        <div className={`mk-box${waiting ? ' mk-faded' : ''}`}><div className="mk-t">TRIN</div>
          <div className="mk-v">{shown.trin == null ? '--' : shown.trin.toFixed(2)}</div><div className="mk-s">under 1 = buyers</div></div>
      </div>
    </Card>
  );
}

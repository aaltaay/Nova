/**
 * NYSE breadth (ADR 053): is the whole market joining the move, or a few big names? Before 09:30 the last session's
 * close, labelled. Every number says what it counts in words (operator ask 2026-10-14: "I don't understand the
 * numbers. What is 1,540?"), and TICK and TRIN read as a sentence first, their names second.
 */
import { count, etTime, signedNum } from './format';
import { Card, Spark } from './parts';
import type { Breadth, BreadthNumbers } from './types';

function share(a: number | null, b: number | null): number | null {
  return a != null && b != null && a + b > 0 ? Math.round((100 * a) / (a + b)) : null;
}

/** One split bar with its words on it: "1,540 up" on green, "1,226 down" on red. */
function Split({ title, up, down, pct, sub }: { title: string; up: string; down: string; pct: number | null; sub: string }) {
  const pa = pct ?? 50;
  return (
    <div className="mk-brow">
      <div className="mk-brow__head">
        <span>{title}</span>
        <span className="mk-brow__sub">{sub}</span>
      </div>
      <div className="mk-ad mk-ad--words" aria-hidden="true">
        <i className="is-up" style={{ width: `${pa}%` }}><span>{up}</span></i>
        <i className="is-down" style={{ width: `${100 - pa}%` }}><span>{down}</span></i>
      </div>
    </div>
  );
}

function Numbers({ n, unchanged, faded }: { n: BreadthNumbers; unchanged: number | null; faded: boolean }) {
  const stocks = share(n.advancing, n.declining);
  const vol = share(n.up_volume, n.down_volume);
  const total = n.advancing != null && n.declining != null ? n.advancing + n.declining + (unchanged ?? 0) : null;
  return (
    <div className={faded ? 'mk-faded' : ''}>
      <p className="mk-breadth__lede" data-testid="market-breadth-lede">
        {stocks == null ? 'No count of rising and falling NYSE stocks yet.'
          : <><b className={`is-${stocks >= 50 ? 'up' : 'down'}`}>{stocks}%</b> of NYSE stocks are up on the day
            {vol == null ? '.' : <>, and <b className={`is-${vol >= 50 ? 'up' : 'down'}`}>{vol}%</b> of the shares traded
              were in rising stocks.</>}</>}
      </p>
      <Split title="Stocks" pct={stocks}
        up={`${count(n.advancing)} up`} down={`${count(n.declining)} down`}
        sub={total == null ? 'NYSE stocks above / below their prior close'
          : `of ${count(total)} NYSE stocks${unchanged ? `, ${count(unchanged)} unchanged` : ''}`} />
      <Split title="Shares traded" pct={vol}
        up={vol == null ? '--' : `${vol}% rising`} down={vol == null ? '--' : `${100 - vol}% falling`}
        sub="where today's NYSE volume went" />
    </div>
  );
}

function tickWords(tick: number | null): string {
  if (tick == null) return 'no reading yet';
  if (tick === 0) return 'as many stocks just ticked up as down';
  return `${count(Math.abs(tick))} more stocks just ticked ${tick > 0 ? 'up' : 'down'} than ${tick > 0 ? 'down' : 'up'}`;
}

function trinWords(trin: number | null): string {
  if (trin == null) return 'no reading yet';
  if (trin > 1) return 'sellers heavier: falling stocks draw more volume';
  if (trin < 1) return 'buyers heavier: rising stocks draw more volume';
  return 'balanced';
}

export function BreadthCard({ breadth }: { breadth: Breadth }) {
  const waiting = breadth.state === 'waiting';
  const shown: BreadthNumbers = waiting && breadth.prior ? breadth.prior : breadth;
  const lastAd = breadth.ad_line.length ? breadth.ad_line[breadth.ad_line.length - 1][1] : null;
  return (
    <Card title="Breadth · NYSE" hint="is the whole market moving, or a few big names?" className="mk-breadth"
      testId="market-breadth"
      extra={<span className="mk-src mk-push" title="IBKR market indicators AD-NYSE, VOL-NYSE, TICK-NYSE, TRIN-NYSE">
        IBKR · NYSE indicators</span>}>
      {breadth.state !== 'ok' ? (
        <p className="mk-wait" role="status">
          {breadth.why}{waiting && breadth.prior ? <> Shown below: <b>{breadth.prior.date}&apos;s last sample</b>, for context.</> : null}
        </p>
      ) : null}
      {breadth.state === 'unavailable' && !breadth.prior ? null
        : <Numbers n={shown} unchanged={waiting ? null : breadth.unchanged} faded={waiting} />}
      <div className="mk-kv">
        <div className="mk-box mk-box--wide"
          title="Rising NYSE stocks minus falling ones, one point a minute. Above the dotted line, more stocks are up.">
          <div className="mk-t">Through the day{breadth.line_since ? `, since ${etTime(breadth.line_since)}` : ''}</div>
          <Spark points={breadth.ad_line} height={28} zero={0} label="NYSE rising minus falling stocks" />
          <div className="mk-s">
            {lastAd == null ? 'rising minus falling stocks'
              : `${signedNum(lastAd, 0)} now · above the dotted line = more stocks up`}
          </div>
        </div>
        <div className={`mk-box${waiting ? ' mk-faded' : ''}`}
          title="NYSE TICK: stocks whose last trade was an uptick minus those on a downtick, this instant. It swings fast; read it as a snapshot.">
          <div className="mk-t">Right now · TICK</div>
          <div className={`mk-v is-${shown.tick == null || shown.tick === 0 ? 'flat' : shown.tick > 0 ? 'up' : 'down'}`}>
            {signedNum(shown.tick, 0)}</div>
          <div className="mk-s">{tickWords(shown.tick)}</div>
        </div>
        <div className={`mk-box${waiting ? ' mk-faded' : ''}`}
          title="NYSE TRIN (Arms index): rising-to-falling stocks divided by their volume ratio. 1 is even; above 1 the volume leans to falling stocks.">
          <div className="mk-t">Volume balance · TRIN</div>
          <div className={`mk-v is-${shown.trin == null || shown.trin === 1 ? 'flat' : shown.trin < 1 ? 'up' : 'down'}`}>
            {shown.trin == null ? '--' : shown.trin.toFixed(2)}</div>
          <div className="mk-s">{trinWords(shown.trin)}</div>
        </div>
      </div>
    </Card>
  );
}

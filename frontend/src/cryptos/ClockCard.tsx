/** The Cryptos page's 24/7 clock (ADR 040): which markets are open across today's ET day, and what is next. */
import { countdown, minutesEt, timeEt } from './format';
import { Card } from './parts';
import { tipLane } from './tips/glossaryDesk';
import { useTip } from './tips/TipHost';
import type { CryptoClock, Lane } from './types';

function Seg({ lane, cls, text }: { lane: Lane; cls: string; text?: string }) {
  return (
    <span className={`cx-lane__seg ${cls}`} style={{ left: `${(lane[0] / 1440) * 100}%`, width: `${((lane[1] - lane[0]) / 1440) * 100}%` }}>
      {text}
    </span>
  );
}

function nowMinutes(clock: CryptoClock): number {
  const [h, m] = timeEt(clock.now).split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

export function ClockCard({ clock }: { clock: CryptoClock }) {
  const tip = useTip();
  const now = nowMinutes(clock);
  const asia = [...clock.lanes.asia].sort((a, b) => b[0] - a[0]);
  const nextStock = clock.stock_next;
  const openRegion = clock.regions.us ? 'US stocks are open.' : clock.regions.europe ? 'Europe is trading.' : clock.regions.asia ? 'Asia is trading.' : 'Only crypto is trading.';
  return (
    <Card title="24/7 clock · ET" className="cx-clock" testId="crypto-clock">
      <div className="cx-clock__body">
        <div className="cx-lane" {...tip(() => tipLane('crypto', clock))}>
          <span className="cx-lane__label">Crypto</span>
          <div className="cx-lane__track">
            <Seg lane={[0, 1440]} cls="is-crypto" text={`Open 24/7 · the crypto day closes at ${clock.crypto_day_start_et} ET (00:00 UTC)`} />
          </div>
        </div>
        <div className="cx-lane" {...tip(() => tipLane('asia', clock))}>
          <span className="cx-lane__label">Asia</span>
          <div className="cx-lane__track">
            {clock.lanes.asia.map((l) => <Seg key={l[0]} lane={l} cls="is-asia" text={l === asia[0] ? 'Tokyo · HK' : undefined} />)}
          </div>
        </div>
        <div className="cx-lane" {...tip(() => tipLane('europe', clock))}>
          <span className="cx-lane__label">Europe</span>
          <div className="cx-lane__track">
            {clock.lanes.europe.map((l) => <Seg key={l[0]} lane={l} cls="is-eu" text="London" />)}
          </div>
        </div>
        <div className="cx-lane" {...tip(() => tipLane('us', clock))}>
          <span className="cx-lane__label">US stocks</span>
          <div className="cx-lane__track">
            {clock.lanes.premarket.map((l) => <Seg key={l[0]} lane={l} cls="is-pre" text="Premarket" />)}
            {clock.lanes.regular.map((l) => <Seg key={l[0]} lane={l} cls="is-rth" text="Open" />)}
            {clock.lanes.after_hours.map((l) => <Seg key={l[0]} lane={l} cls="is-pre" text="After hours" />)}
            {clock.lanes.regular.length === 0 ? <span className="cx-lane__closed">Closed today</span> : null}
          </div>
        </div>
        <div className="cx-lane cx-lane--ticks" {...tip(() => tipLane('funding', clock))}>
          <span className="cx-lane__label">Funding</span>
          <div className="cx-lane__track cx-lane__track--bare">
            {clock.lanes.funding.map(([m]) => (
              <span key={m} className="cx-tick" style={{ left: `${(m / 1440) * 100}%` }} title={minutesEt(m)}>◆</span>
            ))}
            {[0, 4, 8, 12, 16, 20, 24].map((h) => (
              <span key={`h${h}`} className="cx-hour" style={{ left: `${(h / 24) * 100}%` }}>{String(h).padStart(2, '0')}</span>
            ))}
          </div>
        </div>
        <span className="cx-now" style={{ left: `calc(76px + (100% - 76px) * ${now / 1440})` }} {...tip(() => tipLane('now', clock))}>
          <span className="cx-now__tag">Now {timeEt(clock.now)}</span>
        </span>
      </div>
      <p className="cx-clock__line">
        <strong>{openRegion}</strong>{' '}
        {nextStock ? (
          <>
            US stocks {clock.stock_session === 'closed' ? 'closed' : clock.stock_session.replace('_', ' ')} · {nextWords(nextStock.kind)} in{' '}
            <strong>{countdown(nextStock.at - clock.now)}</strong>
          </>
        ) : null}
        {' · '}next funding {timeEt(clock.next_funding)} ET
      </p>
    </Card>
  );
}

function nextWords(kind: string): string {
  return kind === 'premarket' ? 'premarket opens' : kind === 'open' ? 'the open' : kind === 'close' ? 'the close' : 'after hours ends';
}

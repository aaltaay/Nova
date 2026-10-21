/**
 * One currency's hover card on the Forex page (ADR 062, mockup v2): how big its market is (the BIS survey's, labelled),
 * its biggest pair, its price and move, its strength by session, how busy its day is against a normal one, its
 * futures, and anything IBKR refused for it. Shared by the map and the list.
 */
import { firstSentence, localTime, monthWord, signedPct, tone, until, usd } from '../world_board/format';
import { MIXED_DEF, PERIOD_LABEL } from './constants';
import type { Currency, Period, SessionId } from './types';

const SESSION_NAME: Record<SessionId, string> = { asia: 'Asia', london: 'London', new_york: 'New York' };

/** "150.42" / "18.531" / "1.1638": as the market quotes the pair. */
export function rateWord(rate: number | null | undefined): string {
  if (rate == null || !Number.isFinite(rate)) return '--';
  return rate.toFixed(rate >= 100 ? 2 : rate >= 10 ? 3 : 4);
}

function Row({ label, value, t, testId }: { label: string; value: string; t?: string; testId?: string }) {
  return (
    <div className="gb-tip__row" data-testid={testId}>
      <span>{label}</span>
      <b className={t ? `is-${t}` : undefined}>{value}</b>
    </div>
  );
}

export function CurrencyTip({ c, now, period, priced, asOf }: {
  c: Currency; now: number; period: Period; priced: number; asOf: string;
}) {
  const h = c.home;
  const when = h.open ? `its home session open, closes ${until(h.close_at, now)}`
    : h.next_open_at ? `its home session closed, opens ${until(h.next_open_at, now)}` : 'its home session closed';
  const p = c.price;
  const f = c.futures;
  const today = period === '1D' ? 'today' : PERIOD_LABEL[period];
  // "the yen up", "the euro down", "the Australian dollar up"
  const word = /dollar$/.test(c.name) ? c.name : c.name.split(' ').slice(-1)[0].toLowerCase();
  const sessions = c.by_session
    ? (Object.keys(SESSION_NAME) as SessionId[]).filter((k) => c.by_session?.[k] != null)
      .map((k) => `${SESSION_NAME[k]} ${signedPct(c.by_session?.[k], 2)}`).join(' · ')
    : '';
  return (
    <div className="gb-tip fx-tip" role="tooltip" data-testid={`forex-tip-${c.code}`}>
      <div className="gb-tip__head">
        <b>{c.code} · {c.name}</b>
        <span>{c.city} · {localTime(now, c.tz)} local · {when}</span>
      </div>
      <Row label="A day" value={`${usd(c.size.usd)} · ${Math.round(c.size.share_pct)}% of all trades · #${c.size.rank}`}
        testId={`forex-tip-size-${c.code}`} />
      <Row label="Biggest pair" value={`${c.size.pair} · ${usd(c.size.pair_usd)} a day`} />
      {c.code !== 'USD' ? (
        <>
          <Row label="Price" value={p.pair && p.rate != null ? `${p.pair} ${rateWord(p.rate)} · ${signedPct(p.pair_pct, 2)} ${today}` : 'no price'} />
          <Row label="Against the dollar" value={p.vs_usd_pct != null
            ? `${signedPct(p.vs_usd_pct, 2)} (the ${word} ${p.vs_usd_pct >= 0 ? 'up' : 'down'})` : '--'} t={tone(p.vs_usd_pct)} />
        </>
      ) : null}
      <Row label="Strength" value={c.strength_pct != null ? `${signedPct(c.strength_pct, 2)} vs the other ${priced - 1}` : '--'}
        t={tone(c.strength_pct)} />
      {c.range_x != null ? (
        <Row label="Range so far" value={`${c.range_x.toFixed(1)}× a normal day's`} t={c.range_x >= 1.5 ? 'warn' : undefined} />
      ) : null}
      <Row label="Futures" t={tone(f.pressure_usd)}
        value={f.pressure_usd != null ? `${usd(f.pressure_usd, true)} · ${signedPct(f.pressure_pct)} of ${usd(f.traded_usd)}` : 'no futures read'} />
      {c.volume_x != null ? <Row label="Futures volume" value={`${c.volume_x.toFixed(1)}× a normal day so far`} /> : null}
      {sessions ? <div className="gb-tip__src">Strength by session: {sessions}</div> : null}
      <div className="gb-tip__src">
        Size: BIS survey, {monthWord(asOf)} average -- published every three years, not live.
        {p.instrument ? ` Price: ${p.basis === 'future' ? `its future, ${p.instrument.label}` : `IBKR spot, ${p.instrument.label}`}.` : ''}
        {f.basis === 'future' && f.instrument
          ? ` Futures: CME ${f.instrument.label}${f.instrument.contract ? `, ${f.instrument.contract}` : ''} -- the public part of forex.`
          : f.basis === 'sum' ? ' Futures: the other side of every currency\'s CME future.' : ''}
        {p.data_type && p.data_type !== 'live' ? ` · ${p.data_type}` : ''}
      </div>
      {p.error ? <div className="gb-tip__warn" title={p.error}>No price: {firstSentence(p.error)}</div> : null}
      {f.refused.map((r) => (
        <div key={`${r.instrument}`} className="gb-tip__warn" title={r.error ?? undefined}>
          No feed for {r.instrument}: {firstSentence(r.error ?? '')}
        </div>
      ))}
      {c.mixed ? <div className="gb-tip__mixed">≠ {MIXED_DEF}</div> : null}
    </div>
  );
}

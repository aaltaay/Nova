/**
 * The Forex page's top strip (ADR 061): the whole market's size (the BIS survey's, labelled), the day's read, the
 * dollar, and the three sessions -- which currency rose most and fell most in each, beside its desks' share.
 */
import { etTime, monthWord, signedPct, tone, usd } from '../world_board/format';
import { VERDICT_TONE } from './constants';
import type { Dollar, Market, Read, Session } from './types';

const DESK_WORD: Record<string, string> = { 'Hong Kong': 'HK' };
const SHOWN_DESKS = 5;

function AllForex({ market }: { market: Market }) {
  const shown = market.desks.slice(0, SHOWN_DESKS);
  return (
    <div className="gb-kpi fx-all" data-testid="forex-all"
      title={`${market.source}, daily averages in ${monthWord(market.as_of)}: published every three years, not live. ${market.url}`}>
      <span className="gb-kpi__t">All forex <i className="fx-src">BIS survey · {monthWord(market.as_of)} average</i></span>
      <b className="fx-all__big">{usd(market.total_usd)} <small>traded a day</small></b>
      <div className="fx-all__bar" aria-hidden>
        {shown.map((d, i) => (
          <i key={d.name} style={{ width: `${d.share_pct}%`, opacity: 0.95 - i * 0.15 }} title={`${d.name} ${d.share_pct}%`} />
        ))}
      </div>
      <span className="gb-kpi__n">
        desks: {shown.slice(0, 4).map((d) => `${DESK_WORD[d.name] ?? d.name} ${Math.round(d.share_pct)}%`).join(' · ')}
        <br />
        the currencies on this page: {Math.round(market.covered_pct)}% of it
      </span>
    </div>
  );
}

function ReadTile({ read }: { read: Read }) {
  const t = read.verdict ? VERDICT_TONE[read.verdict] : 'flat';
  return (
    <div className={`gb-kpi gb-kpi--read is-${t}`} title={read.rule} data-testid="forex-read">
      <span className="gb-kpi__t">Today's read</span>
      <b className="gb-kpi__headline">{read.headline}</b>
      <span className="gb-kpi__n">
        {read.detail}
        {read.rose.length ? <><br />{read.rose.join(', ')} rose most · {read.fell.join(', ')} fell most</> : null}
      </span>
    </div>
  );
}

function DollarTile({ dollar }: { dollar: Dollar }) {
  return (
    <div className="gb-kpi" data-testid="forex-usd">
      <span className="gb-kpi__t">US dollar</span>
      <div className="gb-kpi__pair">
        <div>
          <small>Strength</small>
          <b className={`is-${tone(dollar.strength_pct)}`}>{signedPct(dollar.strength_pct, 2)}</b>
        </div>
        <div>
          <small>Futures</small>
          <b className={`is-${tone(dollar.pressure_usd)}`}>{usd(dollar.pressure_usd, true)}</b>
        </div>
      </div>
      <span className="gb-kpi__n">
        in {Math.round(dollar.share_pct)}% of all trades · {usd(dollar.size_usd)} a day
        <br />
        up against {dollar.up_against} of {dollar.priced} · down against {dollar.down_against}
      </span>
    </div>
  );
}

const SESSION_WHERE: Record<string, string> = {
  asia: 'until London opens',
  london: 'until New York opens',
  new_york: 'to the FX day\'s end',
};

function SessionTile({ s }: { s: Session }) {
  return (
    <div className="gb-kpi fx-sess-tile" data-testid={`forex-session-${s.id}`}>
      <span className="gb-kpi__t">
        {s.name} {s.state === 'now' ? <i className="fx-sess">now</i> : null}
      </span>
      <div className="gb-kpi__pair">
        <div>
          <small>Rose most</small>
          {s.rose ? <b><span className="fx-code">{s.rose.code}</span> <span className={`is-${tone(s.rose.pct)}`}>{signedPct(s.rose.pct, 2)}</span></b>
            : <b className="is-flat">--</b>}
        </div>
        <div>
          <small>Fell most</small>
          {s.fell ? <b><span className="fx-code">{s.fell.code}</span> <span className={`is-${tone(s.fell.pct)}`}>{signedPct(s.fell.pct, 2)}</span></b>
            : <b className="is-flat">--</b>}
        </div>
      </div>
      <span className="gb-kpi__n">
        {etTime(s.from)}–{etTime(s.to)} ET · {s.state === 'later' ? 'later today' : SESSION_WHERE[s.id]}
        <br />
        {s.desks.label}: {Math.round(s.desks.share_pct)}% of all forex
      </span>
    </div>
  );
}

export function KpiStrip({ market, read, dollar, sessions }: {
  market: Market; read: Read; dollar: Dollar; sessions: Session[];
}) {
  return (
    <div className="gb-kpis fx-kpis" data-testid="forex-kpis">
      <AllForex market={market} />
      <ReadTile read={read} />
      <DollarTile dollar={dollar} />
      {sessions.map((s) => <SessionTile key={s.id} s={s} />)}
    </div>
  );
}

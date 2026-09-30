/**
 * The Cryptos page's lower cards (ADR 040): leverage (funding and forced exits), money flows (stablecoins; ETF
 * flows when a source exists), and what comes next with the day's headlines.
 */
import { FUNDING_CROWDED_PCT, FUNDING_SHORTS_PCT } from './constants';
import { dayTimeEt, funding, listWords, timeEt, usd, usdFine, usdSigned } from './format';
import { Card } from './parts';
import { NEWS_TAG, tipEtfFlows, tipNews, tipNext, tipStablecoins } from './tips/glossaryDesk';
import { tipFunding, tipLiquidations } from './tips/glossaryMarket';
import { useTip } from './tips/TipHost';
import type { CryptoBoard } from './types';

const FUNDING_MAX = 0.06;

export function LeverageCard({ board }: { board: CryptoBoard }) {
  const tip = useTip();
  const lev = board.leverage;
  const crowded = lev.funding.filter((f) => f.funding_8h_pct >= FUNDING_CROWDED_PCT).map((f) => f.symbol);
  const shorts = lev.funding.filter((f) => f.funding_8h_pct <= FUNDING_SHORTS_PCT).map((f) => f.symbol);
  return (
    <Card title="Leverage · perpetuals" className="cx-deriv" testId="crypto-leverage"
      source={{ ids: ['hyperliquid'], label: 'Hyperliquid', sources: board.sources, now: board.clock.now }}>
      <div className="cx-sub">Funding per 8h</div>
      <div className="cx-fund">
        {lev.funding.length === 0 ? <p className="cx-note">Waiting for Hyperliquid.</p> : null}
        {lev.funding.slice(0, 7).map((f) => {
          const r = f.funding_8h_pct;
          const cls = r >= FUNDING_CROWDED_PCT ? 'is-warn' : r <= FUNDING_SHORTS_PCT ? 'is-cool' : 'is-ok';
          const w = Math.min(70, (Math.abs(r) / FUNDING_MAX) * 70);
          return (
            <div key={f.symbol} className="cx-fund__row" {...tip(() => tipFunding(f.symbol, r))}>
              <span className="cx-fund__sym">{f.symbol}</span>
              <span className="cx-fund__track">
                <span className="cx-fund__zero" />
                <span className={`cx-fund__bar ${cls}`} style={r >= 0 ? { left: '30%', width: `${w}%` } : { right: '70%', width: `${Math.min(30, w)}%` }} />
              </span>
              <span className={`cx-fund__val ${cls === 'is-ok' ? '' : cls}`}>{funding(r)}</span>
            </div>
          );
        })}
      </div>
      <p className="cx-note">
        {crowded.length ? <><span className="is-warn">Crowded longs</span> on {listWords(crowded)}: a flush risk. </> : 'No crowded longs. '}
        {shorts.length ? `${listWords(shorts)} shorts pay.` : ''}
      </p>
      <div className="cx-sub">Liquidated · 24h <span className="cx-muted">unknown</span></div>
      <div className="cx-liqbar is-unknown" {...tip(() => tipLiquidations(lev.liquidations_note))}>
        <span>No free source for liquidations yet</span>
      </div>
      <p className="cx-note">
        Open interest on Hyperliquid: {usd(lev.open_interest_usd)} across these coins{lev.btc_open_interest_usd === null ? '' : `, BTC ${usd(lev.btc_open_interest_usd)}`}.
      </p>
    </Card>
  );
}

export function FlowsCard({ board }: { board: CryptoBoard }) {
  const tip = useTip();
  const s = board.flows.stablecoins;
  const days = s?.daily ?? [];
  const max = Math.max(1, ...days.map((d) => Math.abs(d.net_usd)));
  const lastDay = days[days.length - 1];
  const weekNet = days.slice(-7).reduce((sum, d) => sum + d.net_usd, 0);
  return (
    <Card title="Money flows" className="cx-flows" testId="crypto-flows"
      source={{ ids: ['defillama'], label: 'DefiLlama', sources: board.sources, now: board.clock.now }}>
      <div className="cx-sub">Stablecoins minted · net per day</div>
      {days.length ? (
        <div className="cx-bars">
          {days.map((d, i) => (
            <div key={d.date} className="cx-bars__col" {...tip(() => tipStablecoins(s, i))}>
              <div className="cx-bars__pos">{d.net_usd > 0 ? <span className={`cx-bars__bar is-in${i === days.length - 1 ? ' is-last' : ''}`} style={{ height: `${(d.net_usd / max) * 100}%` }} /> : null}</div>
              <div className="cx-bars__neg">{d.net_usd < 0 ? <span className="cx-bars__bar is-out" style={{ height: `${(-d.net_usd / max) * 100}%` }} /> : null}</div>
              <span className="cx-bars__d">{d.date.slice(8)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="cx-chart-empty cx-chart-empty--short">Waiting for DefiLlama.</div>
      )}
      <p className="cx-etf-note" {...tip(() => tipEtfFlows(board.flows.etf_note))}>Spot ETF flows: no free source yet ⓘ</p>
      <div className="cx-flowstats">
        <div {...tip(() => tipStablecoins(s, days.length ? days.length - 1 : null))}>
          <span className="cx-muted">Yesterday</span><strong className={lastDay && lastDay.net_usd < 0 ? 'is-down' : 'is-up'}>{usdSigned(lastDay?.net_usd ?? null)}</strong><span className="cx-muted">minted, net</span>
        </div>
        <div {...tip(() => tipStablecoins(s, null))}>
          <span className="cx-muted">7 days</span><strong className={weekNet < 0 ? 'is-down' : 'is-up'}>{days.length ? usdSigned(weekNet) : '—'}</strong>
          <span className="cx-muted">{days.slice(-7).filter((d) => d.net_usd > 0).length} in, {days.slice(-7).filter((d) => d.net_usd < 0).length} out</span>
        </div>
        <div {...tip(() => tipStablecoins(s, null))}>
          <span className="cx-muted">Stablecoins</span><strong>{usdFine(s?.supply_usd ?? null)}</strong>
          <span className={(s?.change_7d_usd ?? 0) < 0 ? 'is-down' : 'is-up'}>{usdSigned(s?.change_7d_usd ?? null)} 7d</span>
        </div>
      </div>
    </Card>
  );
}

export function NextNewsCard({ board }: { board: CryptoBoard }) {
  const tip = useTip();
  return (
    <Card title="What’s next · news" className="cx-next" testId="crypto-next"
      source={{ ids: ['deribit', 'alpaca'], label: 'Deribit · Alpaca news', sources: board.sources, now: board.clock.now }}>
      <ul className="cx-next__list">
        {board.next.map((n) => (
          <li key={`${n.kind}-${n.at}`} {...tip(() => tipNext(n, board.clock))}>
            <span className="cx-next__when">{dayTimeEt(n.at)}</span>
            <span className={`cx-tag cx-tag--${n.kind}`}>{n.kind === 'crypto_day' ? 'crypto day' : n.kind}</span>
            <span className="cx-next__what">{n.title}{n.detail && n.kind === 'expiry' ? ` · ${n.detail}` : ''}</span>
          </li>
        ))}
      </ul>
      <ul className="cx-news">
        {board.news.length === 0 ? <li className="cx-muted">No crypto headlines in the last 24 hours yet.</li> : null}
        {board.news.map((n) => (
          <li key={`${n.published_ts}-${n.title}`} className={n.kind === 'noise' ? 'is-dim' : undefined} {...tip(() => tipNews(n, board.clock.now))}>
            <span className="cx-news__t">{timeEt(n.published_ts)}</span>
            <span className={`cx-tag cx-tag--${n.kind}`}>{NEWS_TAG[n.kind].label}</span>
            <span className="cx-sym">{n.symbol}</span>
            {n.url ? (
              <a className="cx-news__title" href={n.url} target="_blank" rel="noreferrer noopener">{n.title}</a>
            ) : (
              <span className="cx-news__title">{n.title}</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

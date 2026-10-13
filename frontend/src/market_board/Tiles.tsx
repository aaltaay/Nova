/** The futures and macro tiles (ADR 053): every price IBKR's, each line from 04:00 ET to now. */
import { setNavPage } from '../workspace';
import { price, signedNum, signedPct, signedPts, tone } from './format';
import { Spark } from './parts';
import type { QuoteTile, Session } from './types';

function code(t: QuoteTile): string {
  return t.contract ?? t.symbol;
}

function Tile({ t, session }: { t: QuoteTile; session: Session }) {
  const from = session.open_at - 5.5 * 3600;   // 04:00 ET
  const isSpread = t.kind === 'spread';
  const delayed = t.data_type === 'delayed' || t.data_type === 'delayed_frozen';
  const title = [t.error, t.price_basis === 'mid' ? 'No trade in the snapshot: the quoted midpoint' : null,
    `${t.exchange || 'computed'} via IBKR`].filter(Boolean).join(' · ');
  return (
    <div className={`mk-tile${t.error && t.last == null && !isSpread ? ' is-error' : ''}`} title={title}
      data-testid={`market-tile-${t.id}`}>
      <div className="mk-tile__name">
        <span>{t.label}</span>
        {t.id === 'btc' ? (
          <button type="button" className="mk-link" onClick={() => setNavPage('cryptos')}>Cryptos &rarr;</button>
        ) : (
          <span>{code(t)}{delayed ? <em className="mk-delayed"> delayed</em> : null}</span>
        )}
      </div>
      <div className="mk-tile__px">{isSpread ? signedPts(t.change_pct) : price(t.last)}</div>
      <div className={`mk-tile__chg is-${tone(t.change_pct)}`}>
        {isSpread
          ? t.change_pct == null ? '--' : t.change_pct >= 0 ? 'small caps leading' : 'small caps lagging'
          : t.id === 'tnx' && t.change_pct === 0 && t.last != null
            ? 'unchanged'
            : <>{signedNum(t.change, Math.abs(t.change ?? 0) >= 100 ? 0 : 2)}&nbsp; {signedPct(t.change_pct)}</>}
      </div>
      {t.error && t.last == null && !isSpread ? (
        <p className="mk-tile__error">{t.error}</p>
      ) : (
        <Spark points={t.line} height={36} from={from} to={session.close_at} zero={isSpread ? 0 : t.prev_close}
          mark={session.open_at} label={`${t.label} since 04:00 ET`} />
      )}
    </div>
  );
}

export function QuoteTiles({ quotes, session }: { quotes: QuoteTile[]; session: Session }) {
  return (
    <section className="mk-tiles" data-testid="market-tiles">
      <header className="mk-card__head mk-tiles__head">
        <h3>Futures &amp; macro</h3>
        <span className="mk-hint">
          line runs 04:00 &rarr; close ET, stops at now · dotted = prior close · | = the 09:30 open · IBKR
        </span>
      </header>
      {quotes.map((t) => <Tile key={t.id} t={t} session={session} />)}
    </section>
  );
}

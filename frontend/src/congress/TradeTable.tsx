/**
 * A list of trades as their reports state them (ADR 066): when traded and reported, how many days apart, what the
 * filing says (a range, never a price), whose account, the filer's own words, and the filing itself. Gifts read
 * "Gift", never a sale. With `withMember`, each row names its member (a stock's page, Following).
 */
import { TickerLink } from '../components/TickerLink';
import { Face } from './Face';
import { day, lagClass, rangeText, sideClass, sideWord } from './format';
import { OWNER_WORD } from './constants';
import type { Trade } from './types';

export function TradeTable({ trades, year, withMember = false, onOpenMember, onTicker, onOpenTrader, limit }: {
  trades: Trade[];
  year: number;
  withMember?: boolean;
  onOpenMember?: (bioguide: string) => void;
  onTicker?: (ticker: string) => void;
  onOpenTrader?: (symbol: string) => void;
  limit?: number;
}) {
  const shown = limit ? trades.slice(0, limit) : trades;
  if (!shown.length) return <p className="cg-muted cg-empty">No trades in what the reports hold.</p>;
  return (
    <div className="cg-tablewrap">
      <table className="cg-table" data-testid="congress-trades">
        <thead>
          <tr>
            {withMember ? <th>Member</th> : null}
            <th>Traded</th><th>Stock</th><th>What</th><th>Amount</th><th>Owner</th><th>Reported</th>
            <th className="r">Days after</th><th>The filer&apos;s words</th><th />
          </tr>
        </thead>
        <tbody>
          {shown.map((t) => (
            <tr key={t.id} data-testid={`congress-trade-${t.id}`}>
              {withMember ? (
                <td>
                  <button type="button" className="cg-who" onClick={() => t.bioguide && onOpenMember?.(t.bioguide)}
                    disabled={!t.bioguide} data-why={t.bioguide ? undefined : 'this filer is not matched to a member'}>
                    <Face member={t.member ?? null} name={t.filer} size={24} />
                    <span>{t.member?.name ?? t.filer}</span>
                  </button>
                </td>
              ) : null}
              <td className="cg-nowrap">{day(t.tx, year)}</td>
              <td>
                {t.ticker ? <TickerLink symbol={t.ticker} onOpen={onOpenTrader} className="cg-ticker" look="own" /> : null}
                {t.ticker && onTicker ? (
                  <button type="button" className="cg-asset cg-asset--link" onClick={() => onTicker(t.ticker as string)}
                    title={`Every member who reported ${t.ticker}`}>{t.asset}</button>
                ) : <span className="cg-asset">{t.asset}</span>}
              </td>
              <td className="cg-nowrap">
                <b className={sideClass(t)}>{sideWord(t)}</b>
                {t.kind === 'option' ? <span className="cg-tag">options</span> : null}
                {t.status === 'amended' ? <span className="cg-tag">amended</span> : null}
              </td>
              <td className="cg-nowrap" title={t.amount.text}>{rangeText(t.amount.text)}</td>
              <td>{OWNER_WORD[t.owner] ?? t.owner}</td>
              <td className="cg-nowrap">{day(t.filed, year)}</td>
              <td className={`r ${lagClass(t.lag_days)}`}>{t.lag_days ?? '–'}</td>
              <td className="cg-words">{t.description}</td>
              <td><a className="cg-link" href={t.url} target="_blank" rel="noreferrer">Filing ↗</a></td>
            </tr>
          ))}
        </tbody>
      </table>
      {limit && trades.length > limit ? <p className="cg-muted cg-small">{trades.length - limit} more in the reports.</p> : null}
    </div>
  );
}

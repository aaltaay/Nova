/**
 * Level 2's short chips (ADR 048, #778 step 3), beside the borrow chip (SHORT · Available ~30,000):
 *
 * - **SSR** off, or on with its trigger price ("SSR on · 4.50"). Not known reads "SSR ?" and counts as on: a
 *   short under SSR sells only above the bid. It never blocks a cover.
 * - **COOL-OFF**, while shorts wait out the 10 minutes after an up-halt's resumption (a halt itself is the halt
 *   chip's).
 * - **LIQ**, where IBKR would liquidate the position you hold, long or short.
 *
 * The facts are the short check's own, asked for one share (`useShortFacts`), on a live Trader tab only. Nothing
 * here places or gates: the door decides when a short is sent.
 */
import { liquidationTitle, useShortFacts } from '../ibkr';
import { tipProps } from '../ux';
import {
  SHORT_CHIP_COOLOFF,
  SHORT_CHIP_COOLOFF_TIP,
  SHORT_CHIP_LIQ,
  SHORT_CHIP_SSR_TIP,
} from './constants';
import { useStockReadContext } from './StockReadContext';
import { fmtPx } from './planMath';

function clockEt(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/New_York',
  });
}

export function ShortChips() {
  const ctx = useStockReadContext();
  const live = Boolean(ctx && ctx.active && !ctx.replay);
  const facts = useShortFacts(ctx?.symbol ?? '', live);
  if (!ctx || ctx.replay) return null;
  const ssr = facts.check?.ssr ?? null;
  const halt = facts.check?.halt ?? null;
  const liq = ctx.position?.liquidationPrice ?? null;
  return (
    <>
      {ssr && (
        <span
          className={`sv-short-chip sv-short-chip--ssr is-${ssr.state}`}
          data-testid="short-chip-ssr"
          {...tipProps(ssr.text ? `${ssr.text} ${SHORT_CHIP_SSR_TIP}` : SHORT_CHIP_SSR_TIP, 'SSR (Reg SHO Rule 201)')}
        >
          SSR {ssr.state === 'off' ? 'off' : ssr.state === 'on'
            ? `on${ssr.trigger !== null ? ` · ${fmtPx(ssr.trigger)}` : ''}` : '?'}
        </span>
      )}
      {halt?.state === 'cooloff' && (
        <span
          className="sv-short-chip sv-short-chip--cooloff"
          data-testid="short-chip-cooloff"
          {...tipProps(halt.text || SHORT_CHIP_COOLOFF_TIP, 'Halt cool-off')}
        >
          {SHORT_CHIP_COOLOFF}{halt.until !== null ? ` · ${clockEt(halt.until)}` : ''}
        </span>
      )}
      {liq !== null && ctx.position && (
        <span
          className={`sv-short-chip sv-short-chip--liq${ctx.position.qty < 0 ? ' is-short' : ''}`}
          data-testid="short-chip-liq"
          {...tipProps(liquidationTitle({
            liquidation_price: liq, liquidation_source: ctx.position.liquidationSource ?? null,
          }), 'Liquidation price')}
        >
          {SHORT_CHIP_LIQ} {fmtPx(liq)}
        </span>
      )}
    </>
  );
}

/**
 * The Who trades switch as a chip on the 1-minute chart, under the plan's badge (ADR 037): the mode in a
 * word and its two sides, opening the four choices. A choice Nova cannot take now is locked and says
 * why; the same switch is the row above Level 2.
 */
import { useEffect, useRef, useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { STOCK_MODE_COLORS } from './constants';
import { heldQty } from './momentModel';
import type { StockReadContextValue } from './StockReadContext';
import { MODE_NAMES, MODE_ORDER, MODE_SIDES, modeSentence, sidesOf, switchLock } from './whoTradesModel';
import { switchPending } from './WhoTradesRow';
import './whoTrades.css';

export function WhoTradesChip({ ctx }: { ctx: StockReadContextValue }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const who = ctx.who;
  const view = who.view;
  const mode = view?.mode ?? 'signal';

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('pointerdown', away, true);
    window.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('pointerdown', away, true);
      window.removeEventListener('keydown', key);
    };
  }, [open]);

  const held = heldQty(who.inputs);
  const pending = switchPending(ctx);
  return (
    <div className="sr-whochip" ref={box}>
      <button
        type="button"
        className="sr-whochip__btn"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        {...tipProps(`${modeSentence(mode, ctx.symbol)}\nClick for the four choices.`, `Who trades ${ctx.symbol}`)}
        data-testid="who-trades-chip"
      >
        <i className="sr-who__dot" style={{ background: STOCK_MODE_COLORS[mode] }} aria-hidden="true" />
        <b>{view ? MODE_NAMES[mode] : '…'}</b>
        <span className="sr-whochip__sides">{MODE_SIDES[mode]}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="sr-whochip__menu" role="menu" aria-label={`Who trades ${ctx.symbol}`} data-testid="who-trades-menu">
          {MODE_ORDER.map(m => {
            const on = m === mode;
            const locked = on ? null : switchLock(view, sidesOf(m), { symbol: ctx.symbol, held, pending });
            return (
              <button
                key={m}
                type="button"
                role="menuitemradio"
                aria-checked={on}
                className={`sr-whochip__item${on ? ' sr-whochip__item--on' : ''}`}
                disabled={locked !== null}
                {...whyProps(locked !== null, locked)}
                onClick={() => {
                  setOpen(false);
                  if (!on) {
                    const to = sidesOf(m);
                    void who.setSides(to.buy, to.sell);
                  }
                }}
                data-testid={`who-trades-menu-${m}`}
              >
                <span className="sr-whochip__item-name">
                  <i className="sr-who__dot" style={{ background: STOCK_MODE_COLORS[m] }} aria-hidden="true" />
                  {MODE_NAMES[m]}
                  {on ? ' ✓' : ''}
                </span>
                <span className="sr-whochip__item-sides">{MODE_SIDES[m]}</span>
              </button>
            );
          })}
          <p className="sr-whochip__foot">
            Also above Level 2. Approve and Auto-entry go back to Signal only when Nova restarts; Bot at Strategy is
            the bot&apos;s own list.
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * "Who trades SYMBOL", directly above Level 2 (ADR 037): Buy (You | Nova) and Sell (You | Nova), the mode
 * they make, and -- when something will keep Nova from acting, or a change was refused -- one line that
 * says why. A locked side carries its reason; the same switch is the chip on the 1-minute chart.
 */
import type { DepthMarker } from '../ibkr';
import { tipProps, whyProps } from '../ux';
import { STOCK_MODE_COLORS } from './constants';
import { heldQty } from './momentModel';
import { useStockReadContext, type StockReadContextValue } from './StockReadContext';
import type { StockSide } from './types';
import { MODE_NAMES, MODE_SIDES, modeSentence, switchLock } from './whoTradesModel';
import './whoTrades.css';

/** The desk's own reason to wait before a change: an old backend, a read in flight, a save in flight. */
export function switchPending(ctx: StockReadContextValue): string | null {
  const who = ctx.who;
  if (who.unavailable) return 'This backend is older than the desk and cannot say who trades. Reload the backend.';
  if (who.busy) return who.busy;
  return null;
}

function SideSwitch({ label, value, lockYou, lockNova, onPick, testId }: {
  label: string;
  value: StockSide;
  lockYou: string | null;
  lockNova: string | null;
  onPick: (side: StockSide) => void;
  testId: string;
}) {
  const button = (side: StockSide, locked: string | null) => {
    const on = value === side;
    return (
      <button
        type="button"
        className={`sr-who__side sr-who__side--${side}${on ? ' sr-who__side--on' : ''}`}
        aria-pressed={on}
        disabled={!on && locked !== null}
        {...whyProps(!on && locked !== null, locked)}
        onClick={() => {
          if (!on) onPick(side);
        }}
        data-testid={`${testId}-${side}`}
      >
        {side === 'nova' && !on && locked !== null ? '🔒 ' : ''}
        {side === 'you' ? 'You' : 'Nova'}
      </button>
    );
  };
  return (
    <span className="sr-who__switch" role="group" aria-label={label} data-testid={testId}>
      <span className="sr-who__side-label">{label}</span>
      {button('you', lockYou)}
      {button('nova', lockNova)}
    </span>
  );
}

function WhoTradesRowView({ ctx }: { ctx: StockReadContextValue }) {
  const who = ctx.who;
  const view = who.view;
  const sym = ctx.symbol;
  const mode = view?.mode ?? 'signal';
  const buy = view?.buy ?? 'you';
  const sell = view?.sell ?? 'you';
  const held = heldQty(who.inputs);
  const pending = switchPending(ctx);
  const lock = (to: { buy: StockSide; sell: StockSide }) => switchLock(view, to, { symbol: sym, held, pending });
  const warn = view?.notes.find(n => n.tone === 'warn') ?? null;
  const line = who.error ?? (who.unavailable ? pending : null) ?? warn?.text ?? null;
  const tip = [modeSentence(mode, sym), ...(view?.notes ?? []).map(n => n.text)].join('\n');
  return (
    <section className="sr-who" data-testid="who-trades" aria-label={`Who trades ${sym}`}>
      <div className="sr-who__row">
        <span className="sr-who__kicker" {...tipProps(`Who places each side of the trade on ${sym}: Buy and Sell, each `
          + 'You or Nova.', `Who trades ${sym}`)}>
          <span className="sr-who__kicker-words">Who trades </span>
          {sym}
        </span>
        <SideSwitch
          label="Buy"
          value={buy}
          lockYou={lock({ buy: 'you', sell })}
          lockNova={lock({ buy: 'nova', sell })}
          onPick={side => void who.setSides(side, sell)}
          testId="who-trades-buy"
        />
        <SideSwitch
          label="Sell"
          value={sell}
          lockYou={lock({ buy, sell: 'you' })}
          lockNova={lock({ buy, sell: 'nova' })}
          onPick={side => void who.setSides(buy, side)}
          testId="who-trades-sell"
        />
        <span className="sr-who__mode" {...tipProps(tip, `${MODE_NAMES[mode]} · ${MODE_SIDES[mode]}`)} data-testid="who-trades-mode">
          <i className="sr-who__dot" style={{ background: STOCK_MODE_COLORS[mode] }} aria-hidden="true" />
          {view ? MODE_NAMES[mode] : '…'}
        </span>
      </div>
      {line && (
        <p
          className={`sr-who__note sr-who__note--${who.error ? 'bad' : 'warn'}`}
          {...tipProps(line)}
          data-testid="who-trades-note"
        >
          {line}
        </p>
      )}
    </section>
  );
}

/** The plan's ENTRY / STOP / TARGET for this tab's Level 2; none on a replay desk or the sample desk. */
export function useLevel2Markers(): readonly DepthMarker[] | undefined {
  const ctx = useStockReadContext();
  return ctx && !ctx.replay ? ctx.who.markers : undefined;
}

/** The row; nothing on a replay desk or the sample desk (no stock read there). */
export function WhoTradesRow() {
  const ctx = useStockReadContext();
  if (!ctx || ctx.replay) return null;
  return <WhoTradesRowView ctx={ctx} />;
}

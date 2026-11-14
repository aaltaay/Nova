/**
 * The phone's order ticket (frozen mockup R2-Trade): Quick, where one tap is the order, and Custom, where
 * you choose the side, the type, the price and the size and press one send button.
 *
 * Every Quick button is one of the desk's one-tap actions (tradeActions.ts); what a button will send is
 * written on it. Custom builds the order body the desk's ticket builds. A locked padlock greys the
 * buttons and answers a tap with NOT SENT; a view that is behind holds the buys and says so on them. On a
 * venue the phone does not trade from here (Live, or a Sim replay the phone does not draw) every button is
 * off and says why (`tradeVenueView`).
 */
import { useCallback, useState } from 'react';
import { Lock } from 'lucide-react';
import { TRADE_DEFAULT_STOP_OFFSET_PCT } from '../../constantGroups/trade_defaults';
import { shouldUseOutsideRth } from '../../ibkr/extendedSession';
import type { ManualOrderPayload } from '../../ibkr/orderEntry';
import { seedStopPrice } from '../../ibkr/tradeDefaultSeed';
import { orderCloses } from '../../market_view';
import { plainPrice, priceStep, roundToTick } from '../../utils/priceTick';
import { readPref, writePref } from '../../utils/prefStore';
import { usePhoneSession } from '../PhoneSession';
import { money0 } from '../phoneFormat';
import {
  BUY_LIMIT_OFFSET_WORD,
  buyLimit,
  buyLimitPrice,
  buyMarket,
  priceWord,
  sellAtAsk,
  sellAtBid,
  sellShares,
  stepQty,
} from './tradeActions';
import { SharesSheet, Stepper } from './TradeTicketParts';
import type { PhoneTrade } from './usePhoneTrade';

type Mode = 'Quick' | 'Custom';
type Side = 'BUY' | 'SELL';
type OrderKind = 'MKT' | 'LMT' | 'STP';

const MODE_KEY = 'nova.phone.trade.mode';
const SIZE_KEY = 'nova.phone.trade.size';
const SIZES = [100, 500, 1000] as const;
const MAX_SHARES = 99_999;
const KIND_WORD: Record<OrderKind, string> = { MKT: 'Market', LMT: 'Limit', STP: 'Stop' };
const HELD_WORD = 'held · feed behind';

function readMode(): Mode {
  return readPref<Mode>(MODE_KEY, 'Quick', (raw) => (raw === 'Quick' || raw === 'Custom' ? raw : null));
}

function readSize(): number {
  return readPref<number>(SIZE_KEY, 100, (raw) => (typeof raw === 'number' && Number.isInteger(raw) && raw >= 1 && raw <= MAX_SHARES ? raw : null));
}

export function TradeTicket({ trade, blocked = null, buyingPower, onFlatten, onCancelAll }: {
  trade: PhoneTrade;
  /** Why nothing is sent from this ticket on the desk's venue now, and the short word on its buttons. */
  blocked?: { why: string; word: string } | null;
  buyingPower: number | null;
  /** Ask before flattening (the big warning lives with the dots). */
  onFlatten: () => void;
  onCancelAll: () => void;
}) {
  const session = usePhoneSession();
  const [mode, setModeState] = useState<Mode>(readMode);
  const [size, setSizeState] = useState<number>(readSize);
  const [typing, setTyping] = useState<'quick' | 'custom' | null>(null);
  const [side, setSide] = useState<Side>('BUY');
  const [kind, setKind] = useState<OrderKind>('LMT');
  /** The Custom price as stepped by hand; null follows the book. */
  const [handPrice, setHandPrice] = useState<number | null>(null);
  /** The Custom share count as chosen; null follows the Quick size (a buy) or the whole position (a sell). */
  const [handQty, setHandQty] = useState<number | null>(null);

  const { symbol, bid, ask, heldQty, lag, armed } = trade;
  const offVenue = blocked?.why ?? null;
  const locked = armed === false;
  const long = heldQty > 0 ? heldQty : 0;

  const setMode = (next: Mode): void => {
    writePref(MODE_KEY, next);
    setModeState(next);
  };
  const setSize = (next: number): void => {
    writePref(SIZE_KEY, next);
    setSizeState(next);
  };

  /** Every order button answers a locked padlock the same way: nothing goes, and the banner opens it. */
  const guarded = useCallback((send: () => void) => () => {
    if (locked) {
      session.notify({
        tone: 'refused',
        title: 'NOT SENT · Padlock is locked',
        note: 'Nothing went out. Tap here to unlock.',
        onTap: () => session.setArmed(true),
      });
      return;
    }
    send();
  }, [locked, session]);

  const modeSwitch = (
    <div className="ph-trade__modes" role="group" aria-label="Ticket">
      {(['Quick', 'Custom'] as const).map((m) => (
        <button key={m} type="button" aria-pressed={m === mode} onClick={() => setMode(m)}>{m}</button>
      ))}
    </div>
  );
  const head = (
    <div className="ph-trade__power">
      <span>{long || heldQty < 0 ? 'Buying power' : 'Flat · buying power'} <b>{money0(buyingPower)}</b></span>
      <span className="ph-grow" />
      {modeSwitch}
    </div>
  );

  // A buy while short is a way out (the desk's own rule, `orderCloses`): lag never holds it, here or at the door.
  const buyLag = orderCloses('BUY', false, heldQty) ? null : lag;
  const buyWhy = offVenue ?? buyLag;
  const half = sellShares(long, 50);
  const all = sellShares(long, 100);
  const noShares = `You hold no ${symbol} to sell.`;
  const sellWhy = (shares: number | null, part: string): string | null =>
    offVenue ?? (shares == null ? (long > 0 ? `${part} needs 2 shares.` : noShares) : null);

  const sellButton = (percent: 50 | 100, at: 'ask' | 'bid') => {
    const shares = percent === 50 ? half : all;
    const why = sellWhy(shares, 'Half');
    const part = percent === 50 ? '½' : 'ALL';
    const label = `Sell ${shares ?? ''} ${at === 'ask' ? 'at the Ask' : 'at the Bid'}`.replace('  ', ' ');
    return (
      <button
        key={`${percent}-${at}`}
        type="button"
        className={`ph-trade__btn is-sell-${at}`}
        disabled={Boolean(why)}
        data-why={why ?? undefined}
        data-testid={`phone-sell-${percent}-${at}`}
        onClick={guarded(() => trade.act(label, at === 'ask' ? sellAtAsk(percent) : sellAtBid(percent)))}
      >
        <b>SELL {part}{shares != null ? ` ${shares.toLocaleString('en-US')}` : ''}</b>
        <i>{why ? (blocked ? blocked.word : long > 0 ? 'needs 2 shares' : 'no shares') : at === 'ask' ? `at Ask ${priceWord(ask)} · rests` : `hit Bid ${priceWord(bid)} · now`}</i>
      </button>
    );
  };

  const sizeLabel = SIZES.includes(size as (typeof SIZES)[number]) ? 'Custom' : size.toLocaleString('en-US');
  const quick = (
    <>
      <div className="ph-trade__sizes" role="group" aria-label="Shares to buy">
        {SIZES.map((n) => (
          <button key={n} type="button" aria-pressed={n === size} onClick={() => setSize(n)}>{n}</button>
        ))}
        <button type="button" aria-pressed={sizeLabel !== 'Custom'} aria-label="Another number of shares" onClick={() => setTyping('quick')}>{sizeLabel}</button>
      </div>
      <div className="ph-trade__gridwrap">
        <div className="ph-trade__grid" data-locked={locked ? 'true' : 'false'}>
          <button
            type="button"
            className="ph-trade__btn is-buy"
            disabled={Boolean(buyWhy)}
            data-why={buyWhy ?? undefined}
            data-testid="phone-buy-market"
            onClick={guarded(() => trade.act(`Buy ${size} market`, buyMarket(size)))}
          >
            <b>BUY {size.toLocaleString('en-US')}</b>
            <i>{buyWhy ? (blocked ? blocked.word : HELD_WORD) : 'market · fills now'}</i>
          </button>
          <button
            type="button"
            className="ph-trade__btn is-buy-limit"
            disabled={Boolean(buyWhy)}
            data-why={buyWhy ?? undefined}
            data-testid="phone-buy-limit"
            onClick={guarded(() => trade.act(`Buy ${size} limit`, buyLimit(size)))}
          >
            <b>BUY {size.toLocaleString('en-US')}</b>
            <i>{buyWhy ? (blocked ? blocked.word : HELD_WORD) : `limit ${priceWord(buyLimitPrice(ask))} · ${BUY_LIMIT_OFFSET_WORD}`}</i>
          </button>
          {/* The grid fills by column: the halves, then the whole; each column the Ask over the Bid. */}
          {sellButton(50, 'ask')}
          {sellButton(50, 'bid')}
          {sellButton(100, 'ask')}
          {sellButton(100, 'bid')}
        </div>
        {locked ? (
          <button type="button" className="ph-trade__lockpill" onClick={() => session.setArmed(true)} data-testid="phone-trade-locked">
            <Lock size={15} strokeWidth={2.4} aria-hidden="true" />Locked · tap to unlock
          </button>
        ) : null}
      </div>
      <div className="ph-trade__pair">
        <button
          type="button"
          disabled={Boolean(offVenue) || !long}
          data-why={offVenue ?? (!long ? `A stop protects shares you hold. You hold no ${symbol}.` : undefined)}
          onClick={() => {
            setSide('SELL');
            setKind('STP');
            setHandPrice(null);
            setHandQty(null);
            setMode('Custom');
          }}
        >
          Set a stop…
        </button>
        <button type="button" disabled={Boolean(offVenue)} data-why={offVenue ?? undefined} onClick={onCancelAll} data-testid="phone-cancel-all">Cancel all orders</button>
      </div>
    </>
  );

  // ── Custom ──────────────────────────────────────────────────────────────────────────────
  const buy = side === 'BUY';
  const followed = kind === 'MKT'
    ? (buy ? ask : bid)
    : kind === 'LMT'
      ? (buy ? buyLimitPrice(ask) : ask)
      : seedStopPrice(side, buy ? ask : bid, TRADE_DEFAULT_STOP_OFFSET_PCT);
  const at = buy ? ask : bid;
  const price = kind === 'MKT' ? followed : handPrice ?? (followed != null && at != null ? roundToTick(followed, at) : followed);
  const qty = handQty ?? (buy ? size : all ?? size);
  const stepPrice = (direction: 1 | -1) => (): void => {
    if (price == null) return;
    const next = roundToTick(price + direction * priceStep(price), price);
    if (next > 0) setHandPrice(next);
  };
  const pick = (nextSide: Side, nextKind: OrderKind): void => {
    setSide(nextSide);
    setKind(nextKind);
    setHandPrice(null);
    if (nextSide !== side) setHandQty(null);
  };
  const outside = shouldUseOutsideRth(kind !== 'MKT');
  const how = kind === 'MKT'
    ? `fills now at the ${buy ? 'Ask' : 'Bid'}`
    : kind === 'STP'
      ? `waits for ${priceWord(price)}`
      : buy
        ? (price != null && ask != null && price >= ask ? 'fills now' : 'rests under the Ask')
        : (price != null && bid != null && price <= bid ? 'fills now' : 'rests');
  const about = price != null ? `${kind === 'MKT' ? 'about ' : ''}${money0(qty * price)}` : '';
  const customWhy = offVenue
    ?? (buy && kind !== 'STP' ? buyLag : null)
    ?? (!buy && !long ? noShares : null)
    ?? (kind !== 'MKT' && price == null ? 'Waiting for Level 2 to price it.' : null);
  const sendWords = `${buy ? 'Buy' : 'Sell'} ${qty.toLocaleString('en-US')} · ${kind === 'MKT' ? 'Market' : `${KIND_WORD[kind]} ${priceWord(price)}`}`;
  const sendCustom = guarded(() => {
    const payload: ManualOrderPayload = {
      symbol, side, qty, order_type: kind, outside_rth: outside,
      ...(kind === 'LMT' && price != null ? { limit_price: price } : {}),
      ...(kind === 'STP' && price != null ? { stop_price: price } : {}),
    };
    trade.place(`${buy ? 'Buy' : 'Sell'} ${qty} ${KIND_WORD[kind].toLowerCase()}${kind === 'MKT' ? '' : ` ${priceWord(price)}`}`, payload, kind === 'LMT' ? at : null);
  });
  const chips: readonly { name: string; value: number | null; on: boolean }[] = buy
    ? [...SIZES.map((n) => ({ name: String(n), value: n as number, on: qty === n })), { name: 'Custom', value: null, on: !SIZES.includes(qty as (typeof SIZES)[number]) }]
    : [
        { name: half != null ? `½ ${half}` : '½', value: half, on: half != null && qty === half },
        { name: all != null ? `All ${all}` : 'All', value: all, on: all != null && qty === all },
        { name: '100', value: 100, on: qty === 100 && all !== 100 && half !== 100 },
        { name: 'Custom', value: null, on: false },
      ];

  const custom = (
    <>
      <div className="ph-trade__pick">
        <div role="group" aria-label="Side">
          {(['BUY', 'SELL'] as const).map((s) => (
            <button key={s} type="button" aria-pressed={s === side} data-side={s} onClick={() => pick(s, kind)}>{s === 'BUY' ? 'Buy' : 'Sell'}</button>
          ))}
        </div>
        <div role="group" aria-label="Order type">
          {(['MKT', 'LMT', 'STP'] as const).map((k) => (
            <button key={k} type="button" aria-pressed={k === kind} onClick={() => pick(side, k)}>{KIND_WORD[k]}</button>
          ))}
        </div>
      </div>
      <div className="ph-trade__steps">
        <Stepper
          name="Price"
          label={kind === 'STP' ? 'Stop' : 'Limit'}
          text={kind === 'MKT' ? 'Market' : price != null ? plainPrice(price) : '—'}
          muted={kind === 'MKT'}
          why={kind === 'MKT' ? 'A market order takes the market\'s price. Choose Limit or Stop to set one.' : 'Waiting for Level 2 to price it.'}
          onDown={kind === 'MKT' || price == null ? undefined : stepPrice(-1)}
          onUp={kind === 'MKT' || price == null ? undefined : stepPrice(1)}
        />
        <Stepper
          name="Quantity"
          label="Qty"
          text={qty.toLocaleString('en-US')}
          why={qty > 1 ? `${MAX_SHARES.toLocaleString('en-US')} shares is the most this ticket takes.` : 'One share is the least.'}
          onDown={qty > 1 ? () => setHandQty(stepQty(qty, -1)) : undefined}
          onUp={qty < MAX_SHARES ? () => setHandQty(Math.min(MAX_SHARES, stepQty(qty, 1))) : undefined}
        />
      </div>
      <div className="ph-trade__chips">
        {chips.map((c) => (
          <button
            key={c.name}
            type="button"
            aria-pressed={c.on}
            disabled={c.name !== 'Custom' && c.value == null}
            data-why={c.name !== 'Custom' && c.value == null ? (long > 0 ? 'Half needs 2 shares.' : noShares) : undefined}
            onClick={() => (c.value == null ? setTyping('custom') : setHandQty(c.value))}
          >
            {c.name}
          </button>
        ))}
      </div>
      <div className="ph-trade__gridwrap">
        <button
          type="button"
          className="ph-trade__send"
          data-side={side}
          data-locked={locked ? 'true' : 'false'}
          disabled={Boolean(customWhy)}
          data-why={customWhy ?? undefined}
          data-testid="phone-send"
          onClick={sendCustom}
        >
          <b>{sendWords}</b>
          <i>{customWhy && buy && buyLag && !offVenue ? HELD_WORD : `${about ? `${about} · ` : ''}${how} · ${outside ? 'Day + extended hours' : 'Day'}`}</i>
        </button>
        {locked ? (
          <button type="button" className="ph-trade__lockpill" onClick={() => session.setArmed(true)} data-testid="phone-trade-locked">
            <Lock size={15} strokeWidth={2.4} aria-hidden="true" />Locked · tap to unlock
          </button>
        ) : null}
      </div>
      <div className="ph-trade__pair is-slim">
        <button
          type="button"
          className="is-danger"
          disabled={Boolean(offVenue) || !heldQty}
          data-why={offVenue ?? (!heldQty ? `You hold no ${symbol} to flatten.` : undefined)}
          onClick={onFlatten}
        >
          {heldQty ? `Flatten ${Math.abs(heldQty).toLocaleString('en-US')} at ${heldQty > 0 ? 'Bid' : 'Ask'}` : 'Flatten'}
        </button>
        <button type="button" disabled={Boolean(offVenue)} data-why={offVenue ?? undefined} onClick={onCancelAll}>Cancel all orders</button>
      </div>
    </>
  );

  return (
    <div className="ph-trade__ticket" data-mode={mode} data-testid="phone-ticket">
      {head}
      {mode === 'Quick' ? quick : custom}
      {typing ? (
        <SharesSheet
          start={typing === 'quick' ? size : qty}
          onClose={(shares) => {
            if (shares != null) {
              if (typing === 'quick') setSize(shares);
              else setHandQty(shares);
            }
            setTyping(null);
          }}
        />
      ) : null}
    </div>
  );
}

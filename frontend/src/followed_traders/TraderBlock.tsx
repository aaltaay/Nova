/**
 * One followed trader on the page (approved 2026-10-13, "E2"): their card -- photo, name, on air or off air, the
 * record for the span picked, on today what another feature draws for them (their bot, slots.ts), what they made, and
 * their slot on the stream's bar -- and under it, when they traded that day, one table: their open positions on top,
 * then the closed trades striped by result (operator, 2026-10-15: "make this more compact"). The slot is the live one
 * the feed last saw, or their newest evidence image labelled with its time, never passed off as now. A trader who left
 * the bar (`seen.left_ts`) says so; off air every trade is closed, so none of theirs is open.
 */
import { tipProps } from '../ux/hoverTip';
import {
  FT_BAR_NO_IMAGE,
  FT_BAR_STAND_IN,
  FT_EXIT_IS_IBKR,
  FT_LEFT_BAR,
  FT_LEFT_BAR_WINDOW_TIP,
  FT_LEFT_BAR_TIP,
  FT_NEWEST_FIRST_SHORT,
  FT_NO_POSITIONS,
  FT_NO_TRADES_THAT_DAY,
  FT_NO_TRADES_TODAY,
  FT_OFF_AIR,
  FT_ON_AIR,
  FT_OPEN_COUNT,
  FT_SLOT_LAST_READ,
  FT_SLOT_NOW,
  FT_TRADES,
  FT_TRADES_TODAY,
} from './constants';
import { FeedImage } from './FeedImage';
import { etTime, price } from './format';
import { Face, RecordChips } from './parts';
import { PlFigure } from './PlFigure';
import type { PlSummary } from './plSummary';
import { newestEvidence, type RosterEntry } from './roster';
import { useFollowedSlots } from './slots';
import { TradesTable } from './TradeTables';
import type { FollowedBarSlot, FollowedRecord, FollowedTrade } from './types';

function readText(slot: FollowedBarSlot): string {
  if (slot.positions.length === 0) return FT_NO_POSITIONS;
  return slot.positions.map((p) => `${p.side.toUpperCase()} ${p.symbol} ${price(p.price)}`).join(' · ');
}

function Slot({ entry, version, lastRead }: { entry: RosterEntry; version: number | null; lastRead: string | null }) {
  const { slot, name } = entry;
  const standIn = slot?.image ? null : newestEvidence(entry.trader);
  const read = slot ? `Read as: ${readText(slot)}` : undefined;
  if (slot?.image) {
    return (
      <figure className="ft-slot" data-testid={`ft-slot-${name}`} title={read}>
        <FeedImage path={slot.image} version={version} className="ft-slot__img" alt={`${name}'s slot on the stream's position bar`} />
        <figcaption className="ft-muted ft-xs">{lastRead ? `${FT_SLOT_LAST_READ} · ${lastRead} ET` : FT_SLOT_NOW}</figcaption>
      </figure>
    );
  }
  if (standIn) {
    return (
      <figure className="ft-slot" data-testid={`ft-slot-${name}`} title={read}>
        <FeedImage path={standIn.path} className="ft-slot__img" alt={`${name}'s slot at ${etTime(standIn.ts)}`} />
        <figcaption className="ft-muted ft-xs">{FT_BAR_STAND_IN} · {etTime(standIn.ts)} ET</figcaption>
      </figure>
    );
  }
  if (!slot) return null;
  return (
    <figure className="ft-slot" data-testid={`ft-slot-${name}`} title={read}>
      <span className="ft-img-missing ft-slot__img">{FT_BAR_NO_IMAGE}</span>
    </figure>
  );
}

const NO_TRADES: readonly FollowedTrade[] = [];

interface Props {
  entry: RosterEntry;
  record: FollowedRecord | null;
  /** What they made over the span, P/L per share in %; null with `plWhy` while it cannot be said. */
  pl: PlSummary | null;
  plWhy: string | null;
  isToday: boolean;
  onAir: boolean;
  /** When the feed last updated its capture: the live slot image is asked again with it. */
  captureVersion: number | null;
  /** "As last read · 15:57:12" when the capture is not reading the bar now, or reads it from the stream's past; null
   *  while it reads it live. */
  lastRead: string | null;
  compact: boolean;
  folded: number;
  onShowAll: (name: string) => void;
  onProof: (tradeId: string) => void;
}

export function TraderBlock({ entry, record, pl, plWhy, isToday, onAir, captureVersion, lastRead, compact, folded, onShowAll, onProof }: Props) {
  const { name, trader } = entry;
  const { Trader: Bot } = useFollowedSlots();
  const left = trader?.seen?.left_ts ?? null;
  const last = trader?.seen?.last_ts ?? null;
  // Last seen before they were seen gone, with the bar not read between: when they left is a window, said as one.
  const leftWindow = left !== null && last !== null && last < left;
  const leftTip = leftWindow ? `${FT_LEFT_BAR_TIP}\n${FT_LEFT_BAR_WINDOW_TIP}` : FT_LEFT_BAR_TIP;
  const air = left !== null
    ? <span className="ft-off-air" data-testid={`ft-left-${name}`} {...tipProps(leftTip)}>
        {FT_LEFT_BAR} {leftWindow ? `${etTime(last)}–${etTime(left)}` : etTime(left)}</span>
    : onAir ? <span className="ft-on-air">{FT_ON_AIR}</span> : <span className="ft-off-air">{FT_OFF_AIR}</span>;
  return (
    <section className="ft-card ft-trader" aria-label={name} data-testid={`ft-trader-${name}`}>
      <div className={`ft-trader__card${isToday && Bot ? ' ft-trader__card--slot' : ''}`}>
        <Face path={entry.face} name={name} size="xl" />
        <div className="ft-trader__who">
          <div className="ft-trader__name-row">
            <span className="ft-trader__name">{name}</span>
            {isToday && air}
          </div>
          {trader ? <RecordChips record={record} testId={`ft-record-${name}`} />
            : <span className="ft-pill-chip ft-muted" data-testid={`ft-record-${name}`}>{isToday ? FT_NO_TRADES_TODAY : FT_NO_TRADES_THAT_DAY}</span>}
        </div>
        {isToday && Bot && <Bot name={name} open={trader?.open ?? NO_TRADES} />}
        {trader && <PlFigure summary={pl} unscored={record?.unscored ?? 0} why={plWhy} testId={`ft-pl-${name}`} />}
        <Slot entry={entry} version={captureVersion} lastRead={lastRead} />
      </div>
      {trader && (
        <div className="ft-trader__trades">
          <div className="ft-trades__head">
            <h3 className="ft-block__title">{isToday ? FT_TRADES_TODAY : FT_TRADES}</h3>
            <span className="ft-count">{trader.open.length + trader.closed.length}</span>
            <span className="ft-small">
              {trader.open.length > 0 && <><b className="ft-open-text">{trader.open.length} {FT_OPEN_COUNT}</b> · </>}
              <b className="ft-up-text">{trader.record.wins} won</b> · <b className="ft-down-text">{trader.record.losses} lost</b>
            </span>
            <span className="ft-muted ft-xs">{FT_EXIT_IS_IBKR} · {FT_NEWEST_FIRST_SHORT}</span>
          </div>
          <TradesTable open={trader.open} trades={trader.closed} onProof={onProof} compact={compact} folded={folded}
            onShowAll={() => onShowAll(name)} isToday={isToday} />
        </div>
      )}
    </section>
  );
}

/**
 * One Time & Sales row, its key and the tape's formatters (split out of TimeSalesView).
 * Side is row tint only: ask green | bid red | mid/unknown neutral. A print that does not set a price
 * is a dimmed row whose tooltip says why (AGENTS.md §3, #543).
 */
import { memo } from 'react';
import { TAPE_NO_PRICE_TITLE, TAPE_ROW_HEIGHT_PX, TAPE_UNREPORTED_TITLE } from '../constants';
import { STOCK_VIEW_CLOCK_TIMEZONE } from '../constantGroups/chart_api';
import { tapePrintSetsPrice, type TapePrint, type TapeSide } from './tapeFeed';

/** HH:MM:SS Eastern whatever the browser's zone -- the desk's one clock (QA W24). */
export function fmtTapeTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', {
      hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
    });
  } catch {
    return iso.slice(11, 19) || iso;
  }
}

function fmtPrice(p: number): string {
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function fmtSize(s: number): string {
  return s.toLocaleString('en-US');
}

function sideClass(side: TapeSide | undefined): string {
  switch (side) {
    case 'ask':
      return 'ts-row--ask';
    case 'bid':
      return 'ts-row--bid';
    case 'between':
      return 'ts-row--mid';
    default:
      return 'ts-row--unknown';
  }
}

/**
 * A live print has no id, and a key built from its place in the list changed for every row on every
 * print: React rebuilt all the visible rows each time (4,000 rows a few seconds at a busy open) and the
 * page laid out again under the charts. A print keeps its object from arrival to the ring's end, so
 * the object is its identity.
 */
const liveKeys = new WeakMap<TapePrint, string>();
let liveKeySeq = 0;

export function tapeRowKey(print: TapePrint): string {
  if (print.replayId != null) return print.replayId;
  let key = liveKeys.get(print);
  if (key === undefined) {
    liveKeySeq += 1;
    key = `live-${liveKeySeq}`;
    liveKeys.set(print, key);
  }
  return key;
}

export const TapeRow = memo(function TapeRow({ print }: { print: TapePrint }) {
  // A print that does not set a price is dimmed, and its tooltip says why.
  const setsPrice = tapePrintSetsPrice(print);
  const title = print.unreported ? TAPE_UNREPORTED_TITLE : setsPrice ? undefined : TAPE_NO_PRICE_TITLE;
  return (
    <div
      className={`ts-row ${sideClass(print.side)}${setsPrice ? '' : ' ts-row--no-price'}${
        print.unreported ? ' ts-row--unreported' : ''}`}
      style={{ height: TAPE_ROW_HEIGHT_PX }}
      title={title}
      data-unreported={print.unreported ? '1' : undefined}
      data-sets-price={setsPrice ? undefined : '0'}
    >
      <span className="ts-col--time">{fmtTapeTime(print.time)}</span>
      <span className="ts-col--price">{fmtPrice(print.price)}</span>
      <span className="ts-col--size" data-testid="ts-size" data-size={print.size}>
        {fmtSize(print.size)}
      </span>
      <span className="ts-col--exch">{print.exchange || '—'}</span>
    </div>
  );
}, (previous, next) => {
  const a = previous.print, b = next.print;
  return a === b || (a.replayId != null && a.replayId === b.replayId
    && a.price === b.price && a.size === b.size && a.time === b.time
    && a.exchange === b.exchange && a.side === b.side && a.unreported === b.unreported
    && a.setsPrice === b.setsPrice);
});

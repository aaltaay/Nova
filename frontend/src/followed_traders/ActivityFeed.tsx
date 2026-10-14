/**
 * The Activity column: every entry, add and exit of the day, newest first, one line each with the trader's photo. No
 * screenshots (operator, 2026-10-13): an event opens its stock in the Trader, or, on a desk with no Trader, its trade's
 * Proof, which has them. Only the newest events that fit are drawn; the rest fold into "+N earlier", which opens the
 * whole day's list over the column.
 */
import { useContext, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { tipProps } from '../ux/hoverTip';
import { activity, type ActivityItem, type ActivityVerb } from './activity';
import {
  FT_ACTIVITY,
  FT_ACTIVITY_HINT,
  FT_ACTIVITY_HINT_TRADER,
  FT_ALL_ACTIVITY,
  FT_CLOSE_LIST,
  FT_FOLD_LINE_PX,
  FT_NO_ACTIVITY,
  FT_OPEN_IN_TRADER,
} from './constants';
import { etTime, price } from './format';
import { Face, OpenTraderContext, SideChip } from './parts';
import type { FollowedTrader } from './types';

const VERB_CLASS: Record<ActivityVerb, string> = {
  opened: 'ft-verb--open',
  holding: 'ft-verb--hold',
  'added to': 'ft-verb--add',
  closed: 'ft-verb--close',
};

function Event({ e, face, onProof }: { e: ActivityItem; face: string | null; onProof: (id: string) => void }) {
  const open = useContext(OpenTraderContext);
  return (
    <button type="button" className="ft-event" onClick={() => (open ? open(e.symbol) : onProof(e.tradeId))}
      data-testid={`ft-activity-${e.key}`} {...tipProps(open ? `${FT_OPEN_IN_TRADER}: ${e.symbol}` : null)}>
      <span className="ft-mono ft-muted ft-event__time">{etTime(e.ts)}</span>
      <Face path={face} name={e.trader} size="xs" />
      <span className={`ft-verb ${VERB_CLASS[e.verb]}`}>{e.trader} {e.verb}</span>
      <SideChip side={e.side} />
      <span className="ft-ticker">{e.symbol}</span>
      {e.verb !== 'closed' && e.price !== null && <span className="ft-mono">{price(e.price)}</span>}
      {e.note && <span className="ft-event__note ft-muted ft-small">{e.note}</span>}
    </button>
  );
}

/**
 * How many of the newest events fit the list's height, leaving room for the "+N earlier" line when some do not. While
 * the events or the height are new, every event is drawn and measured once; then only those that fit.
 */
function useFitCount(ref: RefObject<HTMLDivElement | null>, total: number, shape: string): number {
  const [height, setHeight] = useState(0);
  const [fit, setFit] = useState({ key: '', count: total });
  const key = `${shape}|${height}`;
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => setHeight(el.clientHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || fit.key === key) return;
    const bottoms = [...el.querySelectorAll<HTMLElement>('.ft-event')].map((r) => r.offsetTop + r.offsetHeight);
    const fitsAll = bottoms.every((b) => b <= el.clientHeight + 1);
    const room = el.clientHeight - FT_FOLD_LINE_PX;
    setFit({ key, count: fitsAll ? total : bottoms.filter((b) => b <= room).length });
  }, [ref, key, fit.key, total]);
  return fit.key === key ? fit.count : total;
}

export function ActivityFeed({ traders, onProof }: { traders: FollowedTrader[]; onProof: (id: string) => void }) {
  const items = activity(traders);
  const hint = useContext(OpenTraderContext) ? FT_ACTIVITY_HINT_TRADER : FT_ACTIVITY_HINT;
  const faces = new Map(traders.map((t) => [t.name, t.face]));
  const list = useRef<HTMLDivElement>(null);
  const [all, setAll] = useState(false);
  const shape = items.map((e) => e.key).join(',');
  const count = useFitCount(list, items.length, shape);
  const folded = items.length - count;
  return (
    <section className="ft-card ft-activity" aria-labelledby="ft-activity" data-testid="ft-activity">
      <div className="ft-activity__head">
        <h2 id="ft-activity" className="ft-eyebrow">{FT_ACTIVITY}</h2>
        <span className="ft-muted ft-xs">{hint}</span>
      </div>
      <div className="ft-activity__list" ref={list}>
        {items.length === 0 && <div className="ft-activity__empty ft-muted">{FT_NO_ACTIVITY}</div>}
        {items.slice(0, count).map((e) => <Event key={e.key} e={e} face={faces.get(e.trader) ?? null} onProof={onProof} />)}
        {folded > 0 && (
          <button type="button" className="ft-link ft-fold" onClick={() => setAll(true)} data-testid="ft-activity-earlier">
            +{folded} earlier
          </button>
        )}
      </div>
      {all && (
        <div className="ft-overlay" role="dialog" aria-label={FT_ALL_ACTIVITY} data-testid="ft-activity-all">
          <div className="ft-overlay__head">
            <h2 className="ft-eyebrow">{FT_ALL_ACTIVITY}</h2>
            <button type="button" className="ft-btn" onClick={() => setAll(false)}>{FT_CLOSE_LIST}</button>
          </div>
          <div className="ft-overlay__body">
            {items.map((e) => <Event key={e.key} e={e} face={faces.get(e.trader) ?? null} onProof={onProof} />)}
          </div>
        </div>
      )}
    </section>
  );
}

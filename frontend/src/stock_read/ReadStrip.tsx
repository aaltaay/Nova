/**
 * Seven tiles, one per question a trader asks before pressing Buy (ADR 036), and "All": hover or
 * focus a tile for its rows, click it for the sheet at that group, press All for every signal, the
 * bot's decisions today and the history. A tile's dots are its rows, coloured for a long trade.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { tipProps } from '../ux';
import { TILE_NAMES } from './constants';
import { formingProgress, planLane, setupShort } from './planMath';
import { GroupHead, ReadRowList } from './ReadRows';
import type { StockReadContextValue } from './StockReadContext';
import type { ReadGroup, ReadGroupId, StockRead } from './types';

const OPEN_DELAY_MS = 120;
const CLOSE_DELAY_MS = 220;
const POPOVER_MAX_W = 460;
const GAP_PX = 4;

/** A tile's word: the group's verdict, or for a forming setup how far it has got ("Flag 1/2"). */
export function tileValue(g: ReadGroup, read: StockRead): string {
  const plan = read.plan;
  if (g.id === 'setups' && plan?.source === 'setup' && plan.state === 'forming') {
    const prog = formingProgress(planLane(plan, read.setups));
    if (prog) return `${setupShort(plan.setup_type)} ${prog}`;
  }
  return g.value || '—';
}

interface Place {
  left: number;
  top: number;
  width: number;
  maxHeight: number;
  above: boolean;
}

function placeUnder(strip: DOMRect): Place {
  // As wide as its rows read well, right-aligned with the strip: it may reach over the charts.
  const width = Math.min(Math.max(POPOVER_MAX_W, strip.width), window.innerWidth - 16);
  const left = Math.max(8, Math.min(strip.right - width, window.innerWidth - width - 8));
  const below = window.innerHeight - strip.bottom - GAP_PX - 8;
  const above = strip.top - GAP_PX - 8;
  const up = below < 260 && above > below;
  return {
    left,
    top: up ? 8 : strip.bottom + GAP_PX,
    width,
    maxHeight: Math.max(160, up ? above : below),
    above: up,
  };
}

function Popover({ group, total, place, onEnter, onLeave, onAll }: {
  group: ReadGroup;
  total: number;
  place: Place;
  onEnter: () => void;
  onLeave: () => void;
  onAll: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(place.top);
  useLayoutEffect(() => {
    // Above the strip, the popover's own height sets where it starts.
    if (!place.above || !ref.current) {
      setTop(place.top);
      return;
    }
    const h = Math.min(ref.current.scrollHeight, place.maxHeight);
    setTop(Math.max(8, place.maxHeight + 8 - h));
  }, [place, group]);
  return createPortal(
    <div
      ref={ref}
      className="sr-popover"
      role="dialog"
      aria-label={`${group.label}: ${group.value}`}
      style={{ left: place.left, top, width: place.width, maxHeight: place.maxHeight }}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onFocusCapture={onEnter}
      onBlurCapture={onLeave}
      data-testid="stock-read-popover"
    >
      <GroupHead group={group} />
      <ReadRowList rows={group.rows} />
      <button type="button" className="sr-link" onClick={onAll} data-testid="stock-read-popover-all">
        All {total} signals, the bot&apos;s decisions and the history ›
      </button>
    </div>,
    document.body,
  );
}

export function ReadStrip({ ctx }: { ctx: StockReadContextValue }) {
  const read = ctx.read.data;
  const stripRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<ReadGroupId | null>(null);
  const [place, setPlace] = useState<Place | null>(null);
  const timer = useRef<number | null>(null);

  const clearTimer = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const show = useCallback((id: ReadGroupId, delay: number) => {
    clearTimer();
    timer.current = window.setTimeout(() => {
      const rect = stripRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPlace(placeUnder(rect));
      setOpen(id);
    }, delay);
  }, []);
  const hide = useCallback(() => {
    clearTimer();
    timer.current = window.setTimeout(() => setOpen(null), CLOSE_DELAY_MS);
  }, []);
  const keep = useCallback(() => clearTimer(), []);
  useEffect(() => () => clearTimer(), []);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(null);
    };
    const onResize = () => setOpen(null);
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onResize);
    };
  }, [open]);

  if (!read || read.groups.length === 0) return null;
  const total = read.groups.reduce((n, g) => n + g.rows.length, 0);
  const openGroup = read.groups.find(g => g.id === open) ?? null;
  return (
    <div className="sr-strip" ref={stripRef} data-testid="stock-read-strip" role="group" aria-label="The bot's read">
      {read.groups.map(g => (
        <button
          key={g.id}
          type="button"
          className={`sr-tile sr-tile--${g.verdict}${open === g.id ? ' sr-tile--open' : ''}`}
          aria-haspopup="dialog"
          aria-expanded={open === g.id}
          aria-label={`${TILE_NAMES[g.id] ?? g.label}: ${g.value}. ${g.question}`}
          onPointerEnter={() => show(g.id, OPEN_DELAY_MS)}
          onPointerLeave={hide}
          onFocus={() => show(g.id, 0)}
          onBlur={hide}
          onClick={() => {
            setOpen(null);
            ctx.openSheet('signals', g.id);
          }}
          data-testid={`stock-read-tile-${g.id}`}
        >
          <span className="sr-tile__k">{TILE_NAMES[g.id] ?? g.label}</span>
          <span className="sr-tile__v">{tileValue(g, read)}</span>
          <span className="sr-tile__dots" aria-hidden="true">
            {g.rows.map(r => <i key={r.id} className={`sr-dot sr-dot--${r.state}`} />)}
          </span>
        </button>
      ))}
      <button
        type="button"
        className="sr-tile sr-tile--all"
        onClick={() => ctx.openSheet('signals')}
        {...tipProps('Every signal, the bot\'s decisions on it today and its history.', 'All')}
        data-testid="stock-read-all"
      >
        <span className="sr-tile__n">{total}</span>
        <span className="sr-tile__v">All ›</span>
      </button>
      {openGroup && place && (
        <Popover
          group={openGroup}
          total={total}
          place={place}
          onEnter={keep}
          onLeave={hide}
          onAll={() => {
            setOpen(null);
            ctx.openSheet('signals', openGroup.id);
          }}
        />
      )}
    </div>
  );
}

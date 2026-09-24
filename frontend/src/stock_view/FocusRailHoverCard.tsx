/**
 * Focus rail hover card: one card per row. Hovering the row's news circle or
 * its REC / bot dots opens the same card -- the symbol's news since the prior
 * close (the Trader's News panel read, ADR 024), then what the dots mean. It
 * was two cards, and the pointer crossing the dots on its way to a headline
 * swapped the news for the status (operator report 2026-09-24: "I can't move
 * my mouse and read the news because the other widget always takes its
 * place"). The card lives in a portal beside the row and closes when the
 * pointer leaves -- the rail waits a moment so the pointer can move into the
 * card to follow a headline -- and it reads the network only while it shows news.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ItemRow, VerdictBlock } from '../components/CatalystNewsSection';
import { CATALYST_PANEL_HIDDEN_NOISE, CATALYST_PANEL_NO_COMPANY_ITEMS, CATALYST_PANEL_UNREAD } from '../constants';
import {
  FOCUS_RAIL_CARD_BOT_HELD_BODY,
  FOCUS_RAIL_CARD_BOT_HELD_HEAD,
  FOCUS_RAIL_CARD_BOT_QUIET_BODY,
  FOCUS_RAIL_CARD_BOT_QUIET_HEAD,
  FOCUS_RAIL_CARD_GAP_PX,
  FOCUS_RAIL_CARD_MAX_ITEMS,
  FOCUS_RAIL_CARD_NEWS_UNAVAILABLE,
  FOCUS_RAIL_CARD_NO_HEADLINE,
  FOCUS_RAIL_CARD_REC_BODY,
  FOCUS_RAIL_CARD_REC_HEAD,
  focusRailCardMoreItems,
  FOCUS_RAIL_CARD_STATUS_HEAD,
  focusRailCardNewestHeadline,
  focusRailNewsCardTitle,
  focusRailStatusCardTitle,
} from '../constantGroups/trader_chrome';
import { useCatalystPanel } from '../hooks/useCatalystPanel';
import { agoLabel, verdictTooltip } from '../utils/catalystVerdict';
import '../components/catalystNews.css';
import type { FocusRow } from './focusRailState';

export interface CardAnchor {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface FocusRailHover {
  row: FocusRow;
  anchor: CardAnchor;
  /** Show today's news (false on a Sim replay desk, which hides it). */
  news: boolean;
  recording: boolean;
  allowed: boolean;
  held: boolean;
}

/** True when the row has a REC or bot dot the card explains. */
export function hasStatus(hover: Pick<FocusRailHover, 'recording' | 'allowed'>): boolean {
  return hover.recording || hover.allowed;
}

/** Beside the anchor (right, else left), top-aligned, kept inside the viewport. */
export function focusCardPosition(
  anchor: CardAnchor,
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  gap = FOCUS_RAIL_CARD_GAP_PX,
): { left: number; top: number } {
  const right = anchor.right + gap;
  const left = right + size.width <= viewport.width - gap ? right : Math.max(gap, anchor.left - gap - size.width);
  const top = Math.max(gap, Math.min(anchor.top, viewport.height - gap - size.height));
  return { left, top };
}

function Card({ anchor, testId, children, onEnter, onLeave }: {
  anchor: CardAnchor; testId: string; children: ReactNode; onEnter: () => void; onLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  // Re-placed when its size changes: the news card grows when its read lands.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const place = () => {
      const { width, height } = el.getBoundingClientRect();
      const next = focusCardPosition(anchor, { width, height }, { width: window.innerWidth, height: window.innerHeight });
      setPos(prev => (prev && prev.left === next.left && prev.top === next.top ? prev : next));
    };
    place();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(place);
    observer.observe(el);
    return () => observer.disconnect();
  }, [anchor]);
  return createPortal(
    <div ref={ref} role="tooltip" className="focus-rail-card" data-testid={testId}
      style={pos ?? { left: anchor.right, top: anchor.top, visibility: 'hidden' }}
      onMouseEnter={onEnter} onMouseLeave={onLeave}>
      {children}
    </div>,
    document.body,
  );
}

/** What the scanner row itself carries, for a desk that cannot read the list. */
function rowNews(row: FocusRow, nowMs: number): string {
  if (row.verdict !== undefined) return verdictTooltip(row.verdict, nowMs);
  if (!row.headlineAt) return FOCUS_RAIL_CARD_NO_HEADLINE;
  return focusRailCardNewestHeadline(agoLabel(new Date(row.headlineAt).getTime() / 1000, nowMs));
}

function NewsSection({ row }: { row: FocusRow }) {
  const { panel, loading, unavailable, error } = useCatalystPanel(row.symbol);
  const nowMs = Date.now();
  const items = panel?.items ?? [];
  const company = items.filter(item => item.kind !== 'noise');
  const noise = items.length - company.length;
  const shown = company.slice(0, FOCUS_RAIL_CARD_MAX_ITEMS);
  let body: ReactNode = null;
  if (panel) {
    body = (
      <>
        <VerdictBlock v={panel.verdict} nowMs={nowMs} />
        {shown.length > 0 ? (
          <ul className="cn-items focus-rail-card__items">
            {shown.map((item, i) => <ItemRow key={item.item_id ?? i} item={item} nowMs={nowMs} />)}
          </ul>
        ) : (
          <div className="cn-empty">{CATALYST_PANEL_NO_COMPANY_ITEMS}</div>
        )}
        {company.length > shown.length && (
          <div className="focus-rail-card__muted">{focusRailCardMoreItems(company.length - shown.length)}</div>
        )}
        {noise > 0 && <div className="focus-rail-card__muted">{noise} {CATALYST_PANEL_HIDDEN_NOISE}</div>}
      </>
    );
  } else if (unavailable) {
    body = (
      <>
        <div className="focus-rail-card__muted">{FOCUS_RAIL_CARD_NEWS_UNAVAILABLE}</div>
        <div className="focus-rail-card__text">{rowNews(row, nowMs)}</div>
      </>
    );
  } else if (loading || !error) {
    body = <div className="focus-rail-card__muted">{CATALYST_PANEL_UNREAD}</div>;
  }
  return (
    <div className="focus-rail-card__section" data-testid="focus-rail-card-news">
      <div className="focus-rail-card__title">{focusRailNewsCardTitle(row.symbol)}</div>
      {error && <div className="cn-error" role="status">{error}</div>}
      {body}
    </div>
  );
}

/** What the REC / bot dots mean. Under the news it is a section of the same
 * card; alone (a Sim replay desk) it carries the symbol's title. */
function StatusSection({ hover }: { hover: FocusRailHover }) {
  return (
    <div className={`focus-rail-card__section${hover.news ? ' focus-rail-card__section--below' : ''}`}
      data-testid="focus-rail-card-status">
      {hover.news
        ? <div className="focus-rail-card__head">{FOCUS_RAIL_CARD_STATUS_HEAD}</div>
        : <div className="focus-rail-card__title">{focusRailStatusCardTitle(hover.row.symbol)}</div>}
      {hover.recording && (
        <div className="focus-rail-card__status" data-testid="focus-rail-card-rec">
          <i className="focus-rail__dot focus-rail__dot--rec" />
          <div><b>{FOCUS_RAIL_CARD_REC_HEAD}</b><p>{FOCUS_RAIL_CARD_REC_BODY}</p></div>
        </div>
      )}
      {hover.allowed && (
        <div className="focus-rail-card__status" data-testid="focus-rail-card-bot" data-held={hover.held ? '1' : '0'}>
          <i className={`focus-rail__dot focus-rail__dot--bot${hover.held ? '' : ' focus-rail__dot--quiet'}`} />
          <div>
            <b>{hover.held ? FOCUS_RAIL_CARD_BOT_HELD_HEAD : FOCUS_RAIL_CARD_BOT_QUIET_HEAD}</b>
            <p>{hover.held ? FOCUS_RAIL_CARD_BOT_HELD_BODY : FOCUS_RAIL_CARD_BOT_QUIET_BODY}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function FocusRailHoverCard({ hover, onEnter, onLeave }: {
  hover: FocusRailHover; onEnter: () => void; onLeave: () => void;
}) {
  return (
    <Card anchor={hover.anchor} testId="focus-rail-card" onEnter={onEnter} onLeave={onLeave}>
      {hover.news && <NewsSection row={hover.row} />}
      {hasStatus(hover) && <StatusSection hover={hover} />}
    </Card>
  );
}

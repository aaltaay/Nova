/**
 * The Trader context strip: slim symbol tabs (REC dot · symbol · gap ·
 * catalyst chip, pop-out / close on hover) and, on the Sim venue, the
 * scrubber cluster on the same row (`trailing`). Strip is unbounded; live L2
 * tabs stay bright and extras render gray / suspended. + / type stays here.
 * Double-click pops out. Drag docks onto another Nova window (the strip's
 * tooltip says so; the sentence no longer takes row space). When the tabs
 * cannot fit beside the cluster a `›` chevron lists the rest -- the cluster
 * never wraps.
 */
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import {
  TRADER_STRIP_OVERFLOW_ARIA,
  TRADER_STRIP_OVERFLOW_TITLE,
  TRADER_STRIP_TITLE,
  TRADER_STRIP_TITLE_FLOAT,
  TRADER_TAB_ADD_DRAFT_OPEN_WHY,
  TRADER_TAB_ADD_TITLE,
} from '../constants';
import {
  allowTraderTabDrop,
  startTraderTabDrag,
  takeForeignTraderTabDrop,
  type TraderTabDragPayload,
} from '../workspace/traderDesk';
import { openBotSymbolMenu } from '../bot/botSymbolMenuStore';
import {
  getRecordingSymbols,
  isTabRecording,
  subscribeSessionRecord,
} from '../capture/sessionRecordStore';
import { useScannerDockRows } from '../scanner/useScannerDockRows';
import type { TraderMoveLocks } from '../workspace';
import { useSimReplayDesk } from '../sim/useSimReplayDesk';
import { StockViewTab } from './StockViewTab';
import { tabContextFor } from './tabContext';
import { TRADER_DRAFT_SYMBOL } from './traderTabsState';
import { useStripOverflow } from './useStripOverflow';

interface Props {
  tabs: string[];
  live?: string[];
  /** Pinned symbols (ADR 011 preview tabs). Absent: every tab renders pinned. */
  pinned?: string[];
  active: string | null;
  windowId?: string;
  showDock?: boolean;
  showExtract?: boolean;
  dropReady?: boolean;
  /** Right-hand cluster on the same row (the Sim scrubber); never wraps. */
  trailing?: ReactNode;
  /** Moves this workspace cannot make (the sample desk's, #449): no drag, and the reasons. */
  moveLocks?: TraderMoveLocks | null;
  onActivate: (symbol: string) => void;
  onClose: (symbol: string) => void;
  onRename: (from: string, to: string) => void;
  onAddDraft: () => void;
  onExtract: (symbol: string) => void;
  onDock?: (symbol: string) => void;
  /** Pin / unpin a symbol tab (pin icon on the tab, or right-click > Pin). */
  onTogglePin?: (symbol: string) => void;
  onTabDragStart?: (symbol: string) => void;
  onTabDragEnd?: () => void;
  onTabDrop?: (payload: TraderTabDragPayload) => void;
}

export function StockViewTabStrip({
  tabs, live, pinned, active, windowId = '', showDock = false, showExtract = true, dropReady = false, trailing,
  moveLocks = null, onActivate, onClose, onRename, onAddDraft, onExtract, onDock, onTogglePin, onTabDragStart, onTabDragEnd, onTabDrop,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [overflowOpen, setOverflowOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const overflowRef = useRef<HTMLDivElement>(null);
  const scannerRows = useScannerDockRows();
  // Off the live edge the Sim desk is another day: no live gap / news chip (QA W10).
  const replayDesk = useSimReplayDesk();
  // Re-render when the recording set changes; isTabRecording reads the store.
  useSyncExternalStore(subscribeSessionRecord, () => getRecordingSymbols().join(','), () => '');
  const overflowing = useStripOverflow(tabsRef, [tabs.join(','), active, Boolean(trailing)]);

  useEffect(() => {
    if (active === TRADER_DRAFT_SYMBOL) { setEditing(TRADER_DRAFT_SYMBOL); setDraft(''); }
  }, [active, tabs]);

  useEffect(() => {
    if (editing != null) { inputRef.current?.focus(); inputRef.current?.select(); }
  }, [editing]);

  useEffect(() => {
    if (!overflowOpen) return undefined;
    const onDown = (event: MouseEvent) => {
      if (!overflowRef.current?.contains(event.target as Node)) setOverflowOpen(false);
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOverflowOpen(false); };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey); };
  }, [overflowOpen]);

  const commitEdit = () => {
    if (editing == null) return;
    const from = editing;
    setEditing(null);
    onRename(from, draft);
  };
  const cancelEdit = () => {
    if (editing === TRADER_DRAFT_SYMBOL) onClose(TRADER_DRAFT_SYMBOL);
    setEditing(null);
  };

  const liveSet = new Set(live ?? tabs.filter(t => t !== TRADER_DRAFT_SYMBOL));
  const draftOpen = tabs.includes(TRADER_DRAFT_SYMBOL);

  return (
    <div
      className={`sv-tab-strip${dropReady ? ' sv-tab-strip--drop-ready' : ''}${trailing ? ' sv-tab-strip--with-trailing' : ''}`}
      role="tablist"
      aria-label="Trader tabs"
      title={moveLocks?.title ?? (showExtract ? TRADER_STRIP_TITLE : TRADER_STRIP_TITLE_FLOAT)}
      data-testid="sv-tab-strip"
      onDragOver={moveLocks ? undefined : allowTraderTabDrop}
      onDrop={moveLocks ? undefined : (e) => {
        const payload = takeForeignTraderTabDrop(e, windowId);
        if (payload) onTabDrop?.(payload);
      }}
    >
      <div className="sv-tab-strip__tabs" ref={tabsRef} data-testid="sv-tab-strip-tabs">
        {tabs.map(symbol => {
          const isActive = symbol === active;
          const isEditing = editing === symbol;
          const isDraft = symbol === TRADER_DRAFT_SYMBOL;
          const suspended = !isDraft && !liveSet.has(symbol);
          const recording = !isDraft && isTabRecording(symbol);
          // No pinned list means the caller has no preview rule: every tab is kept.
          const isPinned = !isDraft && (pinned ? pinned.includes(symbol) : true);
          const preview = !isDraft && !isPinned;
          const label = isDraft ? 'New' : symbol;
          const togglePin = onTogglePin && !isDraft ? () => onTogglePin(symbol) : undefined;
          return (
            <div
              key={isDraft ? '__draft__' : symbol}
              className={`sv-tab${isActive ? ' sv-tab--active' : ''}${suspended ? ' sv-tab--suspended' : ''}${recording ? ' sv-tab--recording' : ''}${preview ? ' sv-tab--preview' : ''}`}
              role="tab"
              aria-selected={isActive}
              data-suspended={suspended ? '1' : '0'}
              data-pinned={isDraft ? undefined : isPinned ? '1' : '0'}
              data-testid={`sv-tab-${label}`}
              draggable={!isDraft && !isEditing && !moveLocks}
              onDragStart={(e) => {
                if (isDraft || isEditing || moveLocks) { e.preventDefault(); return; }
                startTraderTabDrag(e, { symbol, sourceWindowId: windowId });
                onTabDragStart?.(symbol);
              }}
              onDragEnd={() => onTabDragEnd?.()}
              onContextMenu={(e) => {
                if (isDraft) return;
                e.preventDefault();
                openBotSymbolMenu(
                  symbol,
                  e.clientX,
                  e.clientY,
                  togglePin ? { pinned: isPinned, onTogglePin: togglePin } : undefined,
                );
              }}
            >
              <StockViewTab
                label={label}
                isActive={isActive}
                isDraft={isDraft}
                suspended={suspended}
                recording={recording}
                pinned={isPinned}
                onTogglePin={togglePin}
                context={isDraft || replayDesk ? null : tabContextFor(symbol, scannerRows)}
                showDock={showDock && Boolean(onDock)}
                showExtract={showExtract}
                moveTitle={moveLocks?.title}
                dockWhy={moveLocks?.dock ?? null}
                extractWhy={moveLocks?.extract ?? null}
                editing={isEditing}
                draft={draft}
                inputRef={inputRef}
                onDraftChange={setDraft}
                onCommitEdit={commitEdit}
                onCancelEdit={cancelEdit}
                onActivate={() => onActivate(symbol)}
                onExtract={() => onExtract(symbol)}
                onDock={onDock ? () => onDock(symbol) : undefined}
                onClose={() => onClose(symbol)}
              />
            </div>
          );
        })}
      </div>
      {/* Outside the tabs box, which clips: with four or more tabs "+" was cut
          off with the last tab and sat under the overflow chevron (QA D12).
          Locked, title '' keeps the strip's own title off the reason. */}
      <button
        type="button"
        className="sv-tab-add"
        aria-label="Add ticker tab"
        title={draftOpen ? '' : TRADER_TAB_ADD_TITLE}
        disabled={draftOpen}
        data-why={draftOpen ? TRADER_TAB_ADD_DRAFT_OPEN_WHY : undefined}
        onClick={onAddDraft}
        data-testid="sv-tab-add"
      >
        +
      </button>
      {overflowing && (
        <div className="sv-tab-strip__overflow" ref={overflowRef}>
          <button
            type="button"
            className="sv-tab-strip__overflow-btn"
            aria-label={TRADER_STRIP_OVERFLOW_ARIA}
            title={TRADER_STRIP_OVERFLOW_TITLE}
            aria-expanded={overflowOpen}
            data-testid="sv-tab-strip-overflow"
            onClick={() => setOverflowOpen(open => !open)}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
          {overflowOpen && (
            <div className="sv-tab-strip__overflow-menu" role="menu" data-testid="sv-tab-strip-overflow-menu">
              {tabs.filter(t => t !== TRADER_DRAFT_SYMBOL).map(symbol => (
                <button key={symbol} type="button" role="menuitem"
                  className={`sv-tab-strip__overflow-item${symbol === active ? ' is-active' : ''}`}
                  onClick={() => { setOverflowOpen(false); onActivate(symbol); }}>
                  {symbol}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {trailing && <div className="sv-tab-strip__sep" aria-hidden="true" />}
      {trailing && <div className="sv-tab-strip__trailing" data-testid="sv-tab-strip-trailing">{trailing}</div>}
    </div>
  );
}

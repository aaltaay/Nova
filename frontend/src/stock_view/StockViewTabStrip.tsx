/**
 * Editable symbol chips for Trader View. Strip is unbounded; live L2 tabs
 * stay bright and extras render gray / suspended.
 * + / type stays here. Extract pops out. Drag docks onto another Nova window.
 */
import { useEffect, useRef, useState } from 'react';
import {
  TRADER_TAB_ADD_TITLE,
  TRADER_TAB_DOCK_ARIA,
  TRADER_TAB_DOCK_LABEL,
  TRADER_TAB_DOCK_TITLE,
  TRADER_TAB_DRAG_TITLE,
  TRADER_TAB_EXTRACT_ARIA,
  TRADER_TAB_EXTRACT_LABEL,
  TRADER_TAB_EXTRACT_TITLE,
  TRADER_TAB_LABEL_TITLE,
  TRADER_TAB_LABEL_TITLE_FLOAT,
  TRADER_TAB_STRIP_HINT,
  TRADER_TAB_STRIP_HINT_FLOAT,
  TRADER_TAB_SUSPENDED_TITLE,
} from '../constants';
import {
  allowTraderTabDrop,
  startTraderTabDrag,
  takeForeignTraderTabDrop,
  type TraderTabDragPayload,
} from '../workspace/traderDesk';
import { TRADER_DRAFT_SYMBOL } from './traderTabsState';

interface Props {
  tabs: string[];
  live?: string[];
  active: string | null;
  windowId?: string;
  showDock?: boolean;
  showExtract?: boolean;
  dropReady?: boolean;
  onActivate: (symbol: string) => void;
  onClose: (symbol: string) => void;
  onRename: (from: string, to: string) => void;
  onAddDraft: () => void;
  onExtract: (symbol: string) => void;
  onDock?: (symbol: string) => void;
  onTabDragStart?: (symbol: string) => void;
  onTabDragEnd?: () => void;
  onTabDrop?: (payload: TraderTabDragPayload) => void;
}

export function StockViewTabStrip({
  tabs,
  live,
  active,
  windowId = '',
  showDock = false,
  showExtract = true,
  dropReady = false,
  onActivate,
  onClose,
  onRename,
  onAddDraft,
  onExtract,
  onDock,
  onTabDragStart,
  onTabDragEnd,
  onTabDrop,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (active === TRADER_DRAFT_SYMBOL) {
      setEditing(TRADER_DRAFT_SYMBOL);
      setDraft('');
    }
  }, [active, tabs]);

  useEffect(() => {
    if (editing != null) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const commitEdit = () => {
    if (editing == null) return;
    const from = editing;
    setEditing(null);
    onRename(from, draft);
  };

  const cancelEdit = () => {
    if (editing === TRADER_DRAFT_SYMBOL) {
      onClose(TRADER_DRAFT_SYMBOL);
    }
    setEditing(null);
  };

  const liveSet = new Set(live ?? tabs.filter(t => t !== TRADER_DRAFT_SYMBOL));

  return (
    <div
      className={`sv-tab-strip${dropReady ? ' sv-tab-strip--drop-ready' : ''}`}
      role="tablist"
      aria-label="Trader tabs"
      data-testid="sv-tab-strip"
      onDragOver={allowTraderTabDrop}
      onDrop={(e) => {
        const payload = takeForeignTraderTabDrop(e, windowId);
        if (payload) onTabDrop?.(payload);
      }}
    >
      {tabs.map(symbol => {
        const isActive = symbol === active;
        const isEditing = editing === symbol;
        const isDraft = symbol === TRADER_DRAFT_SYMBOL;
        const suspended = !isDraft && !liveSet.has(symbol);
        const label = isDraft ? 'New' : symbol;
        return (
          <div
            key={isDraft ? '__draft__' : symbol}
            className={`sv-tab${isActive ? ' sv-tab--active' : ''}${suspended ? ' sv-tab--suspended' : ''}`}
            role="tab"
            aria-selected={isActive}
            data-suspended={suspended ? '1' : '0'}
            data-testid={`sv-tab-${label}`}
            draggable={!isDraft && !isEditing}
            onDragStart={(e) => {
              if (isDraft || isEditing) {
                e.preventDefault();
                return;
              }
              startTraderTabDrag(e, { symbol, sourceWindowId: windowId });
              onTabDragStart?.(symbol);
            }}
            onDragEnd={() => onTabDragEnd?.()}
          >
            {isEditing ? (
              <input
                ref={inputRef}
                className="sv-tab__input"
                value={draft}
                aria-label="Edit ticker"
                spellCheck={false}
                onChange={e => setDraft(e.target.value.toUpperCase())}
                onBlur={commitEdit}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    commitEdit();
                  } else if (e.key === 'Escape') {
                    e.preventDefault();
                    cancelEdit();
                  }
                }}
              />
            ) : (
              <button
                type="button"
                className="sv-tab__label"
                onClick={() => onActivate(symbol)}
                onDoubleClick={e => {
                  e.preventDefault();
                  if (!isDraft && showExtract) onExtract(symbol);
                }}
                title={
                  isDraft
                    ? 'Type a ticker, then Enter'
                    : suspended
                      ? TRADER_TAB_SUSPENDED_TITLE
                      : (showExtract ? TRADER_TAB_LABEL_TITLE : TRADER_TAB_LABEL_TITLE_FLOAT)
                }
              >
                {label}
              </button>
            )}
            {!isDraft && showDock && onDock && (
              <button
                type="button"
                className="sv-tab__dock"
                aria-label={`${TRADER_TAB_DOCK_ARIA} (${label})`}
                title={TRADER_TAB_DOCK_TITLE}
                data-testid={`sv-tab-dock-${label}`}
                onClick={e => {
                  e.stopPropagation();
                  onDock(symbol);
                }}
              >
                {TRADER_TAB_DOCK_LABEL}
              </button>
            )}
            {!isDraft && showExtract && (
              <button
                type="button"
                className="sv-tab__extract"
                aria-label={`${TRADER_TAB_EXTRACT_ARIA} (${label})`}
                title={TRADER_TAB_EXTRACT_TITLE}
                data-testid={`sv-tab-extract-${label}`}
                onClick={e => {
                  e.stopPropagation();
                  onExtract(symbol);
                }}
              >
                {TRADER_TAB_EXTRACT_LABEL}
              </button>
            )}
            <button
              type="button"
              className="sv-tab__close"
              aria-label={`Close ${label}`}
              onClick={e => {
                e.stopPropagation();
                if (isEditing) cancelEdit();
                else onClose(symbol);
              }}
            >
              ×
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="sv-tab-add"
        aria-label="Add ticker tab"
        title={TRADER_TAB_ADD_TITLE}
        disabled={tabs.includes(TRADER_DRAFT_SYMBOL)}
        onClick={onAddDraft}
        data-testid="sv-tab-add"
      >
        +
      </button>
      <span className="sv-tab-strip__hint" data-testid="sv-tab-strip-hint" title={TRADER_TAB_DRAG_TITLE}>
        {showExtract ? TRADER_TAB_STRIP_HINT : TRADER_TAB_STRIP_HINT_FLOAT}
      </span>
    </div>
  );
}

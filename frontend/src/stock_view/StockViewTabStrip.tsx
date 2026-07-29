/**
 * Editable symbol chips for Trader View (max TRADER_MAX_TABS).
 */
import { useEffect, useRef, useState } from 'react';
import { TRADER_MAX_TABS } from '../constantGroups/trader_view';
import { TRADER_DRAFT_SYMBOL } from './traderTabsState';

interface Props {
  tabs: string[];
  active: string | null;
  onActivate: (symbol: string) => void;
  onClose: (symbol: string) => void;
  onRename: (from: string, to: string) => void;
  onAddDraft: () => void;
}

export function StockViewTabStrip({
  tabs,
  active,
  onActivate,
  onClose,
  onRename,
  onAddDraft,
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

  const beginEdit = (symbol: string) => {
    setEditing(symbol);
    setDraft(symbol === TRADER_DRAFT_SYMBOL ? '' : symbol);
  };

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

  const atCap = tabs.filter(t => t !== TRADER_DRAFT_SYMBOL).length >= TRADER_MAX_TABS
    && !tabs.includes(TRADER_DRAFT_SYMBOL);

  return (
    <div className="sv-tab-strip" role="tablist" aria-label="Trader tabs" data-testid="sv-tab-strip">
      {tabs.map(symbol => {
        const isActive = symbol === active;
        const isEditing = editing === symbol;
        const label = symbol === TRADER_DRAFT_SYMBOL ? 'New' : symbol;
        return (
          <div
            key={symbol === TRADER_DRAFT_SYMBOL ? '__draft__' : symbol}
            className={`sv-tab${isActive ? ' sv-tab--active' : ''}`}
            role="tab"
            aria-selected={isActive}
            data-testid={`sv-tab-${label}`}
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
                onDoubleClick={() => beginEdit(symbol)}
                title="Double-click to edit ticker"
              >
                {label}
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
        title={atCap ? `Max ${TRADER_MAX_TABS} Level 2 tabs` : 'Add ticker'}
        disabled={atCap || tabs.includes(TRADER_DRAFT_SYMBOL)}
        onClick={onAddDraft}
        data-testid="sv-tab-add"
      >
        +
      </button>
    </div>
  );
}

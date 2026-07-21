/** Stock View header symbol chip — double-click to type a new ticker. */
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import {
  STOCK_VIEW_SYMBOL_EDIT_ARIA,
  STOCK_VIEW_SYMBOL_EDIT_TITLE,
  STOCK_VIEW_SYMBOL_MAX_LEN,
} from '../constants';
import { fmtPct } from '../utils/quoteFormat';

interface Props {
  symbol: string;
  displaySymbol?: string;
  mainPrice: number | null;
  mainChangeAbs: number | null;
  mainChangePct: number | null;
  isPositive: boolean;
  refreshing: boolean;
  onCommit: (symbol: string) => void;
}

function normalizeSymbol(raw: string): string {
  return raw.trim().toUpperCase();
}

export function StockViewSymbolChip({
  symbol,
  displaySymbol,
  mainPrice,
  mainChangeAbs,
  mainChangePct,
  isPositive,
  refreshing,
  onCommit,
}: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const skipBlurCommit = useRef(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(symbol);

  useEffect(() => {
    if (!editing) setDraft(symbol);
  }, [symbol, editing]);

  useEffect(() => {
    if (!editing) return;
    const el = inputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, [editing]);

  function beginEdit() {
    skipBlurCommit.current = false;
    setDraft(symbol);
    setEditing(true);
  }

  function cancelEdit() {
    skipBlurCommit.current = true;
    setDraft(symbol);
    setEditing(false);
  }

  function commitEdit() {
    if (skipBlurCommit.current) {
      skipBlurCommit.current = false;
      return;
    }
    const next = normalizeSymbol(draft);
    setEditing(false);
    if (!next || next === normalizeSymbol(symbol)) {
      setDraft(symbol);
      return;
    }
    onCommit(next);
  }

  function onInputKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitEdit();
      // Blur follows Enter — skip the duplicate onBlur pass.
      skipBlurCommit.current = true;
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelEdit();
    }
  }

  function onChipKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      beginEdit();
    }
  }

  if (editing) {
    return (
      <div
        className="sv-header__symbol-chip sv-header__symbol-chip--editing"
        data-testid="stock-view-symbol-chip-edit"
        aria-live="polite"
      >
        <label className="sv-header__symbol-edit-label" htmlFor={inputId}>
          {STOCK_VIEW_SYMBOL_EDIT_ARIA}
        </label>
        <input
          id={inputId}
          ref={inputRef}
          className="sv-header__symbol-input"
          type="text"
          value={draft}
          maxLength={STOCK_VIEW_SYMBOL_MAX_LEN}
          autoComplete="off"
          spellCheck={false}
          aria-label={STOCK_VIEW_SYMBOL_EDIT_ARIA}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={onInputKeyDown}
          onBlur={commitEdit}
        />
      </div>
    );
  }

  const shown = displaySymbol ?? symbol;

  return (
    <div
      className="sv-header__symbol-chip"
      data-testid="stock-view-symbol-chip"
      role="button"
      tabIndex={0}
      title={STOCK_VIEW_SYMBOL_EDIT_TITLE}
      aria-label={`${shown}. ${STOCK_VIEW_SYMBOL_EDIT_TITLE}`}
      onDoubleClick={e => {
        e.preventDefault();
        beginEdit();
      }}
      onKeyDown={onChipKeyDown}
    >
      <span className="sv-header__symbol">{shown}</span>
      {mainChangeAbs != null && (
        <span className="sv-header__trend" aria-hidden>
          {isPositive ? '▲' : '▼'}
        </span>
      )}
      {mainPrice != null ? (
        <span className="sv-header__price">${mainPrice.toFixed(2)}</span>
      ) : (
        <span className="sv-header__price sv-header__price--missing" title="Waiting for IBKR quote">
          —
        </span>
      )}
      {mainChangeAbs != null ? (
        <span
          className={`sv-header__change ${(mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}
        >
          {mainChangeAbs >= 0 ? '+' : ''}
          {mainChangeAbs.toFixed(2)} ({fmtPct(mainChangePct)})
        </span>
      ) : (
        <span className="sv-header__change sv-header__change--missing" title="Day change needs prior close">
          —
        </span>
      )}
      {refreshing && <span className="sv-header__updating">Updating…</span>}
      <span className="sv-header__symbol-hint" aria-hidden>
        ▾
      </span>
    </div>
  );
}

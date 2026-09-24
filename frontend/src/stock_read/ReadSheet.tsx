/** The read sheet (ADR 036): slides over the right side of the Trader tab's charts with three tabs --
 * every signal, the bot's decisions on the symbol today, its history. Escape or ✕ closes it. */
import { useEffect } from 'react';
import { DecisionsTab } from './DecisionsTab';
import { HistoryTab } from './HistoryTab';
import { SignalsTab } from './SignalsTab';
import { useStockReadContext, type SheetTab } from './StockReadContext';
import type { DecisionEvent } from './types';
import './stockRead.css';
import './stockReadSheet.css';

const TABS: { id: SheetTab; label: string }[] = [
  { id: 'signals', label: 'Signals' },
  { id: 'decisions', label: 'Decisions' },
  { id: 'history', label: 'History' },
];

export function StockReadSheet() {
  const ctx = useStockReadContext();
  const open = ctx?.sheet.open === true;
  const closeSheet = ctx?.closeSheet;
  useEffect(() => {
    if (!open || !closeSheet) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSheet();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, closeSheet]);
  if (!ctx || !open) return null;
  const read = ctx.read.data;
  const show = (e: DecisionEvent) => {
    ctx.setLayers({ setups: true });
    ctx.focusAt(e.ts, e);
    ctx.closeSheet();
  };
  return (
    <aside className="sr-sheet" role="dialog" aria-label={`${ctx.symbol}: the bot's read`} data-testid="stock-read-sheet">
      <header className="sr-sheet__head">
        <div className="sr-sheet__tabs" role="tablist">
          {TABS.map(t => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={ctx.sheet.tab === t.id}
              className="sr-sheet__tab"
              onClick={() => ctx.openSheet(t.id)}
              data-testid={`stock-read-tab-${t.id}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <span className="sr-sheet__sym">{ctx.symbol}</span>
        <button type="button" className="sr-sheet__close" aria-label="Close" onClick={ctx.closeSheet}
          data-testid="stock-read-sheet-close">
          ✕
        </button>
      </header>
      <div className="sr-sheet__body">
        {ctx.sheet.tab === 'signals' && (read
          ? <SignalsTab read={read} focusGroup={ctx.sheet.group} />
          : <p className="sr-empty">{ctx.read.error ?? 'Reading…'}</p>)}
        {ctx.sheet.tab === 'decisions' && <DecisionsTab state={ctx.decisions} onShow={show} />}
        {ctx.sheet.tab === 'history' && <HistoryTab state={ctx.history} />}
      </div>
    </aside>
  );
}

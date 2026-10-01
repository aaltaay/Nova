/**
 * Who trades -- the stocks Nova may buy on this venue (ADR 037, ADR 042 F): every stock
 * not at Signal only (`GET /api/stock-mode`: Bot, Auto-entry, Approve) and the bot's own
 * list, with the facts that decide whether Nova can act on each: its mode, does Nova
 * hold the Level 2 line and who holds it, the last price and change, where every
 * setup's scanner has it, and every note that keeps Nova from acting. Adding a stock
 * here sets it to Bot through the stock-mode rules; a refusal is shown in the backend's
 * own words, right here. The scanners and Eyes watch every HOD Momo name whatever this
 * list says.
 */
import { useState, type RefObject } from 'react';
import {
  BOT_ALLOWLIST_ADD_BUTTON,
  BOT_SYMBOL_ALLOWLIST_CAP,
  botTradeRemoveLabel,
} from '../constantGroups/bot';
import {
  BOTS_CHG_TITLE,
  BOTS_ENTRIES_TODAY,
  BOTS_ENTRIES_TODAY_TIP,
  BOTS_L2_HELD,
  BOTS_L2_HELD_TITLE,
  BOTS_L2_HELD_VIA,
  BOTS_L2_OPEN,
  BOTS_L2_OPEN_TITLE,
  BOTS_LAST_TITLE,
  BOTS_MODE_LABELS,
  BOTS_MODE_TIPS,
  BOTS_OPEN_STOCK,
  BOTS_OPEN_STOCK_TITLE,
  BOTS_STOCK_MODES_UNREAD,
  BOTS_SYMBOL_BUSY_WHY,
  BOTS_SYMBOL_EMPTY_WHY,
  BOTS_SYMBOLS_CAP,
  BOTS_SYMBOLS_CAP_WHY,
  BOTS_SYMBOLS_EMPTY,
  BOTS_SYMBOLS_NOTE,
  BOTS_SYMBOLS_PLACEHOLDER,
  BOTS_SYMBOLS_SUB,
  BOTS_SYMBOLS_TITLE,
} from '../constantGroups/bots_page';
import { useRecordingSymbols } from '../capture/sessionRecordStore';
import { useLiveScannerFeedOptional } from '../scanner/ScannerDataContext';
import { formatSignedPct, pctTone, scannerRowFor } from '../stock_view/tabContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { rowRank, rowsBySymbol, setupShort, setupTypeOf, stateWords, useSetupsBoard, type SetupRow } from '../setups';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { tipProps } from '../ux/hoverTip';
import { prose } from './botsPageFormat';
import type { StockModeRow } from './stockModesApi';
import { toggleBotStock, useBotAllowlist } from './useBotAllowlist';
import type { StockModesState } from './useStockModes';
import type { BotSession } from './types';

/** The element id of the add box, for the hero's "add a stock" chip. */
export const BOTS_SYMBOL_INPUT_ID = 'bots-symbol-input';

function heldLines(session: BotSession): Set<string> {
  const gate = (session.gates ?? []).find(g => g.id === 'depth_lines');
  const held = gate?.detail?.held;
  return new Set(Array.isArray(held) ? held.filter((s): s is string => typeof s === 'string') : []);
}

/** How many setup chips a symbol's cell shows before "+N". */
const SETUP_CHIPS = 2;

function SetupChips({ rows, connected }: { rows: readonly SetupRow[] | undefined; connected: boolean }) {
  if (!rows?.length) {
    const tip = connected
      ? 'On no setup\'s board right now: no scanner has it forming, armed, near, triggered or failed.'
      : 'The setup scanner is not connected.';
    return <span className="bots-muted" {...tipProps(tip)}>—</span>;
  }
  const more = rows.length - SETUP_CHIPS;
  return (
    <span className="bots-setupchips">
      {rows.slice(0, SETUP_CHIPS).map(row => {
        const w = stateWords(row);
        const broke = row.state === 'near' && Boolean(row.setup?.detail?.broke_at);
        return (
          <span key={setupTypeOf(row)} className={`bots-state bots-state--${broke ? 'broke' : row.state}`}
            data-testid={`bots-symbol-setup-${row.symbol}-${setupTypeOf(row)}`} {...tipProps(w.tip, w.title)}>
            {setupShort(setupTypeOf(row))} · {w.text}
          </span>
        );
      })}
      {more > 0 ? (
        <span className="bots-muted" {...tipProps(rows.slice(SETUP_CHIPS).map(r => stateWords(r).title).join('\n'))}>+{more}</span>
      ) : null}
    </span>
  );
}

/** One stock Nova may buy, with the facts its row shows. */
interface StockLine {
  sym: string;
  mode: string;
  view: StockModeRow | null;
  /** Its rows on the setup board, most advanced first. */
  mine: SetupRow[] | undefined;
  last: number | null;
  chg: number | null;
  held: boolean;
  via: 'record' | 'trader' | null;
}

const COLUMNS: SortColumns<StockLine> = {
  symbol: l => l.sym,
  mode: l => l.mode,
  l2: l => l.held,
  last: l => l.last,
  chg: l => l.chg,
  // Its most advanced setup first: near, armed, triggered, ... (rowRank is lowest-first).
  setups: l => (l.mine?.length ? -rowRank(l.mine[0]) : null),
};

function fmtLast(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

/** Every note that keeps Nova from acting on it, and the last thing Nova did or skipped. */
function NotesCell({ view }: { view: StockModeRow | null }) {
  if (!view) return <span className="bots-muted">—</span>;
  const lines = [
    ...(view.buyLock ? [view.buyLock] : []),
    ...view.notes.map(n => n.text),
  ];
  const tip = [...lines, view.lastEvent ? `Last: ${view.lastEvent.text}` : '', view.size ? `Size: ${view.size}` : '']
    .filter(Boolean).join('\n');
  if (!lines.length) {
    return view.lastEvent
      ? <span className="bots-muted bots-notes-last" {...tipProps(tip, view.symbol)}>{view.lastEvent.text}</span>
      : <span className="bots-chip bots-chip--ok" {...tipProps(tip || 'Nothing keeps Nova from acting on it.', view.symbol)}>clear</span>;
  }
  const warn = Boolean(view.buyLock) || view.notes.some(n => n.tone === 'warn');
  return (
    <span className={`bots-chip bots-notes-chip${warn ? ' bots-chip--warn' : ''}`} data-testid={`bots-symbol-notes-${view.symbol}`}
      {...tipProps(tip, `${view.symbol} · what keeps Nova from acting`)}>
      {lines[0]}{lines.length > 1 ? ` · +${lines.length - 1}` : ''}
    </span>
  );
}

interface Props {
  session: BotSession;
  modes: StockModesState;
  onOpenL2: (symbol: string) => void;
  inputRef?: RefObject<HTMLInputElement | null>;
}

export function BotSymbolsCard({ session, modes, onOpenL2, inputRef }: Props) {
  const { symbols } = useBotAllowlist();
  const { traderLiveTabs } = useWorkspace();
  const recording = useRecordingSymbols();
  const feed = useLiveScannerFeedOptional();
  const stream = useSetupsBoard();
  const [draft, setDraft] = useState('');
  const [asking, setAsking] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const held = heldLines(session);
  const rows = rowsBySymbol(stream?.board?.rows);
  const atCap = symbols.length >= BOT_SYMBOL_ALLOWLIST_CAP;
  const views = new Map(modes.rows.filter(r => r.mode !== 'signal').map(r => [r.symbol, r]));
  const all = [...new Set([...symbols, ...views.keys()])];
  const lines: StockLine[] = all.map(sym => {
    const mine = rows.get(sym);
    const board = scannerRowFor(sym, feed);
    const last = mine?.[0]?.last_price ?? board?.price ?? null;
    const prev = board?.prev_close ?? null;
    const view = views.get(sym) ?? null;
    return {
      sym,
      mode: view?.mode ?? 'bot',
      view,
      mine,
      last,
      chg: last != null && prev ? (last / prev - 1) * 100 : null,
      held: held.has(sym),
      via: recording.includes(sym) ? 'record' : traderLiveTabs.includes(sym) ? 'trader' : null,
    };
  });
  const { rows: sorted, sort, onSort } = useTableSort('bot.symbols', lines, COLUMNS);
  const entries = session.entries_today;
  const addWhy = asking ? BOTS_SYMBOL_BUSY_WHY : atCap ? BOTS_SYMBOLS_CAP_WHY(BOT_SYMBOL_ALLOWLIST_CAP) : !draft.trim() ? BOTS_SYMBOL_EMPTY_WHY : null;

  async function change(sym: string, op: 'add' | 'remove') {
    setAsking(sym);
    setRefusal(null);
    const answer = await toggleBotStock(sym, op, true);
    setAsking(null);
    if (answer.error) setRefusal(answer.error);
    else {
      if (op === 'add') setDraft('');
      modes.refresh();
    }
  }

  return (
    <section className="bots-card" data-testid="bots-symbols">
      <header className="bots-card__head">
        <h3>{BOTS_SYMBOLS_TITLE}</h3>
        <span className="bots-card__sub">{BOTS_SYMBOLS_SUB}</span>
      </header>
      <p className="bots-muted bots-symbols__note" data-testid="bots-symbols-note">{BOTS_SYMBOLS_NOTE}</p>
      {entries ? (
        <p className="bots-symbols__entries" data-testid="bots-entries-today" {...tipProps(BOTS_ENTRIES_TODAY_TIP, 'Nova\'s buys today')}>
          {BOTS_ENTRIES_TODAY(entries.count, entries.cap, entries.approved)}
        </p>
      ) : null}
      {modes.error ? <p className="bots-hero__error" role="alert" data-testid="bots-stock-modes-error">{BOTS_STOCK_MODES_UNREAD(modes.error)}</p> : null}
      {all.length === 0 ? (
        <p className="bots-empty">{BOTS_SYMBOLS_EMPTY}</p>
      ) : (
        <table className="bots-table">
          <thead>
            <tr>
              <SortTh col="symbol" sort={sort} onSort={onSort}>Symbol</SortTh>
              <SortTh col="mode" sort={sort} onSort={onSort}>Who</SortTh>
              <SortTh col="l2" sort={sort} onSort={onSort}>Level 2</SortTh>
              <SortTh col="last" sort={sort} onSort={onSort} className="num" title={BOTS_LAST_TITLE}>Last</SortTh>
              <SortTh col="chg" sort={sort} onSort={onSort} className="num" title={BOTS_CHG_TITLE}>Chg</SortTh>
              <SortTh col="setups" sort={sort} onSort={onSort}
                {...tipProps('Where each setup\'s scanner has the stock right now, most advanced first. Hover a chip for what it means.', 'Setups')}>
                Setups
              </SortTh>
              <th>Notes</th>
              <th aria-label="Change" />
            </tr>
          </thead>
          <tbody>
            {sorted.map(({ sym, mode, view, mine, last, chg, held: isHeld, via }) => (
              <tr key={sym} data-testid={`bots-symbol-${sym}`}>
                <td className="bots-sym">{sym}</td>
                <td>
                  <span className={`bots-chip bots-mode bots-mode--${mode}`} data-testid={`bots-symbol-mode-${sym}`}
                    {...tipProps(BOTS_MODE_TIPS[mode] ?? mode, BOTS_MODE_LABELS[mode] ?? mode)}>
                    {BOTS_MODE_LABELS[mode] ?? mode}
                  </span>
                </td>
                <td>
                  {isHeld ? (
                    <span className="bots-chip bots-chip--ok" title={BOTS_L2_HELD_TITLE}>
                      {BOTS_L2_HELD}{via ? ` · ${BOTS_L2_HELD_VIA[via]}` : ''}
                    </span>
                  ) : (
                    <button type="button" className="bots-chip bots-chip--warn" data-testid={`bots-symbol-open-l2-${sym}`}
                      title={BOTS_L2_OPEN_TITLE} onClick={() => onOpenL2(sym)}>
                      {BOTS_L2_OPEN}
                    </button>
                  )}
                </td>
                <td className="num">{fmtLast(last)}</td>
                <td className={`num bots-chg bots-chg--${pctTone(chg)}`}>{chg == null ? '—' : formatSignedPct(chg)}</td>
                <td><SetupChips rows={mine} connected={Boolean(stream?.connected)} /></td>
                <td><NotesCell view={view} /></td>
                <td>
                  {mode === 'bot' ? (
                    <button type="button" className="bots-x" aria-label={botTradeRemoveLabel(sym)} title={botTradeRemoveLabel(sym)}
                      data-testid={`bots-symbol-remove-${sym}`} disabled={asking != null}
                      data-why={asking != null ? BOTS_SYMBOL_BUSY_WHY : undefined}
                      onClick={() => void change(sym, 'remove')}>×</button>
                  ) : (
                    <button type="button" className="bots-linkbtn" data-testid={`bots-symbol-open-${sym}`}
                      title={BOTS_OPEN_STOCK_TITLE} onClick={() => onOpenL2(sym)}>{BOTS_OPEN_STOCK}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form className="bots-add" onSubmit={e => { e.preventDefault(); const t = draft.trim().toUpperCase(); if (t && addWhy == null) void change(t, 'add'); }}>
        <input
          id={BOTS_SYMBOL_INPUT_ID}
          ref={inputRef}
          data-testid="bots-symbol-input"
          value={draft}
          placeholder={atCap ? BOTS_SYMBOLS_CAP(BOT_SYMBOL_ALLOWLIST_CAP) : BOTS_SYMBOLS_PLACEHOLDER}
          autoComplete="off"
          spellCheck={false}
          disabled={atCap}
          data-why={atCap ? BOTS_SYMBOLS_CAP_WHY(BOT_SYMBOL_ALLOWLIST_CAP) : undefined}
          onChange={e => { setDraft(e.target.value.toUpperCase()); setRefusal(null); }}
        />
        <button type="submit" className="bots-btn" data-testid="bots-symbol-add" disabled={addWhy != null}
          data-why={addWhy ?? undefined}>
          {BOT_ALLOWLIST_ADD_BUTTON}
        </button>
      </form>
      {refusal ? <p className="bots-hero__error" role="alert" data-testid="bots-symbol-refusal">{prose(refusal)}</p> : null}
    </section>
  );
}

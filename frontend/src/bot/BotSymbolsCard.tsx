/**
 * The bot's symbols (the allowlist) with the facts that decide whether it can
 * act on each: does Nova hold the Level 2 line (BOT_NO_DEPTH_LINE) and who
 * holds it, the last price and change, and where the first-pullback scanner
 * has it. An empty list means the bot does nothing. Add here, or right-click a
 * scanner row, Trader tab or chart.
 */
import { useState, type RefObject } from 'react';
import { BOT_ALLOWLIST_ADD_BUTTON, BOT_ALLOWLIST_CHIP_REMOVE, BOT_SYMBOL_ALLOWLIST_CAP } from '../constants';
import {
  BOTS_CHG_TITLE,
  BOTS_L2_HELD,
  BOTS_L2_HELD_TITLE,
  BOTS_L2_HELD_VIA,
  BOTS_L2_OPEN,
  BOTS_L2_OPEN_TITLE,
  BOTS_LAST_TITLE,
  BOTS_SYMBOLS_CAP,
  BOTS_SYMBOLS_EMPTY,
  BOTS_SYMBOLS_PLACEHOLDER,
  BOTS_SYMBOLS_SUB,
  BOTS_SYMBOLS_TITLE,
} from '../constantGroups/bots_page';
import { useRecordingSymbols } from '../capture/sessionRecordStore';
import { useLiveScannerFeedOptional } from '../scanner/ScannerDataContext';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import { formatSignedPct, pctTone, scannerRowFor } from '../stock_view/tabContext';
import { setupCell } from '../strategy/watchlistFormat';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { useBotAllowlist } from './useBotAllowlist';
import type { BotSession } from './types';
import '../strategy/watchlist.css';

/** The element id of the add box, for the hero's "add a symbol" chip. */
export const BOTS_SYMBOL_INPUT_ID = 'bots-symbol-input';

function heldLines(session: BotSession): Set<string> {
  const gate = (session.gates ?? []).find(g => g.id === 'depth_lines');
  const held = gate?.detail?.held;
  return new Set(Array.isArray(held) ? held.filter((s): s is string => typeof s === 'string') : []);
}

function fmtLast(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

interface Props {
  session: BotSession;
  onOpenL2: (symbol: string) => void;
  inputRef?: RefObject<HTMLInputElement | null>;
}

export function BotSymbolsCard({ session, onOpenL2, inputRef }: Props) {
  const { symbols, add, remove } = useBotAllowlist();
  const { traderLiveTabs } = useWorkspace();
  const recording = useRecordingSymbols();
  const feed = useLiveScannerFeedOptional();
  const stream = useSetupsBoard();
  const [draft, setDraft] = useState('');
  const held = heldLines(session);
  const rows = new Map((stream?.board?.rows ?? []).map(r => [r.symbol, r]));
  const atCap = symbols.length >= BOT_SYMBOL_ALLOWLIST_CAP;

  async function onAdd() {
    const ticker = draft.trim().toUpperCase();
    if (!ticker || atCap) return;
    if (await add(ticker)) setDraft('');
  }

  return (
    <section className="bots-card" data-testid="bots-symbols">
      <header className="bots-card__head">
        <h3>{BOTS_SYMBOLS_TITLE}</h3>
        <span className="bots-card__sub">{BOTS_SYMBOLS_SUB}</span>
      </header>
      {symbols.length === 0 ? (
        <p className="bots-empty">{BOTS_SYMBOLS_EMPTY}</p>
      ) : (
        <table className="bots-table">
          <thead>
            <tr>
              <th>Symbol</th><th>Level 2</th><th className="num" title={BOTS_LAST_TITLE}>Last</th>
              <th className="num" title={BOTS_CHG_TITLE}>Chg</th><th>First pullback</th><th aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {symbols.map(sym => {
              const row = rows.get(sym);
              const board = scannerRowFor(sym, feed);
              const cell = setupCell(row, Boolean(stream?.connected));
              const last = row?.last_price ?? board?.price ?? null;
              const prev = board?.prev_close ?? null;
              const chg = last != null && prev ? (last / prev - 1) * 100 : null;
              const via = recording.includes(sym) ? 'record' : traderLiveTabs.includes(sym) ? 'trader' : null;
              return (
                <tr key={sym} data-testid={`bots-symbol-${sym}`}>
                  <td className="bots-sym">{sym}</td>
                  <td>
                    {held.has(sym) ? (
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
                  <td><span className={`wl-badge wl-badge--${cell.tone || 'plain'}`} title={cell.title}>{cell.text}</span></td>
                  <td>
                    <button type="button" className="bots-x" aria-label={`${BOT_ALLOWLIST_CHIP_REMOVE} ${sym}`}
                      data-testid={`bots-symbol-remove-${sym}`} onClick={() => void remove(sym)}>×</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <form className="bots-add" onSubmit={e => { e.preventDefault(); void onAdd(); }}>
        <input
          id={BOTS_SYMBOL_INPUT_ID}
          ref={inputRef}
          data-testid="bots-symbol-input"
          value={draft}
          placeholder={atCap ? BOTS_SYMBOLS_CAP(BOT_SYMBOL_ALLOWLIST_CAP) : BOTS_SYMBOLS_PLACEHOLDER}
          autoComplete="off"
          spellCheck={false}
          disabled={atCap}
          onChange={e => setDraft(e.target.value.toUpperCase())}
        />
        <button type="submit" className="bots-btn" data-testid="bots-symbol-add" disabled={atCap || !draft.trim()}>
          {BOT_ALLOWLIST_ADD_BUTTON}
        </button>
      </form>
    </section>
  );
}

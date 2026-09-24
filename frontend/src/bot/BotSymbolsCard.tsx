/**
 * The bot's symbols (the allowlist) with the facts that decide whether it can
 * act on each: does Nova hold the Level 2 line (BOT_NO_DEPTH_LINE) and who
 * holds it, the last price and change, and where every setup's scanner has it
 * (ADR 031: one chip per setup, each explaining itself on hover). An empty list
 * means the bot does nothing. Add here, or right-click a scanner row, Trader tab
 * or chart.
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
  BOTS_SYMBOL_EMPTY_WHY,
  BOTS_SYMBOLS_CAP,
  BOTS_SYMBOLS_CAP_WHY,
  BOTS_SYMBOLS_EMPTY,
  BOTS_SYMBOLS_PLACEHOLDER,
  BOTS_SYMBOLS_SUB,
  BOTS_SYMBOLS_TITLE,
} from '../constantGroups/bots_page';
import { useRecordingSymbols } from '../capture/sessionRecordStore';
import { useLiveScannerFeedOptional } from '../scanner/ScannerDataContext';
import { formatSignedPct, pctTone, scannerRowFor } from '../stock_view/tabContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { rowsBySymbol, setupShort, setupTypeOf, stateWords, useSetupsBoard, type SetupRow } from '../setups';
import { tipProps } from '../ux/hoverTip';
import { useBotAllowlist } from './useBotAllowlist';
import type { BotSession } from './types';

/** The element id of the add box, for the hero's "add a symbol" chip. */
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
  const rows = rowsBySymbol(stream?.board?.rows);
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
              <th className="num" title={BOTS_CHG_TITLE}>Chg</th>
              <th {...tipProps('Where each setup\'s scanner has the symbol right now, most advanced first. Hover a chip for what it means.', 'Setups')}>Setups</th>
              <th aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {symbols.map(sym => {
              const mine = rows.get(sym);
              const board = scannerRowFor(sym, feed);
              const last = mine?.[0]?.last_price ?? board?.price ?? null;
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
                  <td><SetupChips rows={mine} connected={Boolean(stream?.connected)} /></td>
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
          data-why={atCap ? BOTS_SYMBOLS_CAP_WHY(BOT_SYMBOL_ALLOWLIST_CAP) : undefined}
          onChange={e => setDraft(e.target.value.toUpperCase())}
        />
        <button type="submit" className="bots-btn" data-testid="bots-symbol-add" disabled={atCap || !draft.trim()}
          data-why={atCap ? BOTS_SYMBOLS_CAP_WHY(BOT_SYMBOL_ALLOWLIST_CAP) : !draft.trim() ? BOTS_SYMBOL_EMPTY_WHY : undefined}>
          {BOT_ALLOWLIST_ADD_BUTTON}
        </button>
      </form>
    </section>
  );
}

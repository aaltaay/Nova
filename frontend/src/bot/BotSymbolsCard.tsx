/**
 * The bot's symbols (the allowlist) with the two facts that decide whether it
 * can act on each: does Nova hold the Level 2 line (BOT_NO_DEPTH_LINE), and
 * where the first-pullback scanner has it. An empty list means the bot does
 * nothing. Add here, or right-click a scanner row, Trader tab or chart.
 */
import { useState } from 'react';
import {
  BOT_ALLOWLIST_ADD_BUTTON,
  BOT_ALLOWLIST_CHIP_REMOVE,
  BOT_SYMBOL_ALLOWLIST_CAP,
} from '../constants';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import { setupCell } from '../strategy/watchlistFormat';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { useBotAllowlist } from './useBotAllowlist';
import type { BotSession } from './types';
import '../strategy/watchlist.css';

function heldLines(session: BotSession): Set<string> {
  const gate = (session.gates ?? []).find(g => g.id === 'depth_lines');
  const held = gate?.detail?.held;
  return new Set(Array.isArray(held) ? held.filter((s): s is string => typeof s === 'string') : []);
}

function fmtLast(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

export function BotSymbolsCard({ session }: { session: BotSession }) {
  const { symbols, add, remove } = useBotAllowlist();
  const { openStockView } = useWorkspace();
  const stream = useSetupsBoard();
  const [draft, setDraft] = useState('');
  const held = heldLines(session);
  const rows = new Map((stream?.board?.rows ?? []).map(r => [r.symbol, r]));
  const atCap = symbols.length >= BOT_SYMBOL_ALLOWLIST_CAP;

  async function onAdd() {
    const ticker = draft.trim();
    if (!ticker || atCap) return;
    await add(ticker);
    setDraft('');
  }

  return (
    <section className="bots-card" data-testid="bots-symbols">
      <header className="bots-card__head">
        <h3>Symbols</h3>
        <span className="bots-card__sub">empty list = bot does nothing</span>
      </header>
      {symbols.length === 0 ? (
        <p className="bots-empty">No symbols yet. The bot only ever looks at the symbols listed here.</p>
      ) : (
        <table className="bots-table">
          <thead>
            <tr><th>Symbol</th><th>Level 2</th><th className="num">Last</th><th>First pullback</th><th aria-label="Remove" /></tr>
          </thead>
          <tbody>
            {symbols.map(sym => {
              const row = rows.get(sym);
              const cell = setupCell(row, Boolean(stream?.connected));
              const isHeld = held.has(sym);
              return (
                <tr key={sym} data-testid={`bots-symbol-${sym}`}>
                  <td className="bots-sym">{sym}</td>
                  <td>
                    {isHeld ? (
                      <span className="bots-held">Held</span>
                    ) : (
                      <button type="button" className="bots-link" onClick={() => openStockView(sym)}
                        title="Open its Level 2 in the Trader so the bot can read the tape">
                        Not held · Open L2
                      </button>
                    )}
                  </td>
                  <td className="num">{fmtLast(row?.last_price)}</td>
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
          data-testid="bots-symbol-input"
          value={draft}
          placeholder="Add ticker… (or right-click a scanner row, Trader tab or chart)"
          autoComplete="off"
          spellCheck={false}
          disabled={atCap}
          onChange={e => setDraft(e.target.value)}
        />
        <button type="submit" className="bots-btn" data-testid="bots-symbol-add" disabled={atCap || !draft.trim()}>
          {BOT_ALLOWLIST_ADD_BUTTON}
        </button>
      </form>
    </section>
  );
}

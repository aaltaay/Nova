/** The Watchlist table: Five Pillars as letter chips, the row's market facts, today's catalyst,
 * where the setup scanner has it, and the bot allowlist dot. Nothing here places an order. */
import { useMemo, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import { ScannerRowNumCell, ScannerRowNumHeader } from '../components/ScannerTable';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import {
  WATCHLIST_BOT_OFF_TITLE,
  WATCHLIST_BOT_ON_TITLE,
  WATCHLIST_FILTER_LABELS,
  WATCHLIST_FOOTNOTE,
} from '../constants';
import { fmtPct, fmtRvol, fmtVolume, pctToneClass } from '../utils/quoteFormat';
import {
  applyFilter,
  newsCell,
  pillarLetter,
  setupCell,
  setupsBySymbol,
  summarize,
  type Cell,
  type WatchlistFilter,
} from './watchlistFormat';
import type { WatchlistEntry } from './types';
import type { SetupRow } from '../setups/types';
import './watchlist.css';

const FILTERS: WatchlistFilter[] = ['all', 'pillars5', 'setup_live', 'allowlist'];

function fmtLast(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v < 1 ? v.toFixed(4) : v.toFixed(2);
}

function PillarLetters({ entry }: { entry: WatchlistEntry }) {
  const p = entry.five_pillars;
  return (
    <span className="wl-pillars" title={`${p.pass_count} of ${p.total} pillars pass`}>
      <span className="wl-pillar-dots">
        {p.pillars.map(pc => (
          <i key={pc.name} className={`wl-pd ${pc.passed ? 'wl-pd--y' : 'wl-pd--n'}`} title={pc.detail}>
            {pillarLetter(pc.name)}
          </i>
        ))}
      </span>
      <span className="wl-pillar-count">{p.pass_count}/{p.total}</span>
    </span>
  );
}

function ToneCell({ cell, badge = false }: { cell: Cell; badge?: boolean }) {
  const cls = badge ? `wl-badge wl-badge--${cell.tone || 'plain'}` : `wl-tone wl-tone--${cell.tone || 'plain'}`;
  return <span className={cls} title={cell.title}>{cell.text}</span>;
}

function WatchlistRow({ entry, index, setup, following, allowed, onToggleBot, selected, onSelect, onOpenTrading }: {
  entry: WatchlistEntry;
  index: number;
  setup: SetupRow | undefined;
  following: boolean;
  allowed: boolean;
  onToggleBot: (symbol: string, on: boolean) => void;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const rvol = fmtRvol(entry.rel_volume);
  return (
    <SelectableTableRow
      symbol={entry.symbol}
      selected={selected}
      onSelect={onSelect}
      onOpenTrading={onOpenTrading}
      openOnRowClick={false}
    >
      <ScannerRowNumCell index={index} />
      <td>
        <SymbolSelectButton symbol={entry.symbol} selected={selected} onSelect={onSelect} onOpenTrading={onOpenTrading} />
      </td>
      <td><PillarLetters entry={entry} /></td>
      <td className="num">{fmtLast(entry.price)}</td>
      <td className={`num ${pctToneClass(entry.change_pct)}`}>{fmtPct(entry.change_pct ?? null, '—')}</td>
      <td className="num" title={entry.rvol_source ? `RVOL over the ${entry.rvol_source} average daily volume` : undefined}>
        {rvol ?? '—'}
      </td>
      <td className="num">{fmtVolume(entry.float_shares)}</td>
      <td><ToneCell cell={newsCell(entry)} /></td>
      <td className="wl-score-cell" title="Weighted 0-100 composite of % change, RVOL, float and news freshness">
        <span className="wl-score-bar"><i style={{ width: `${Math.max(0, Math.min(100, entry.composite_score))}%` }} /></span>
        <span className="wl-score-num">{entry.composite_score.toFixed(0)}</span>
      </td>
      <td><ToneCell cell={setupCell(setup, following)} badge /></td>
      <td className="wl-bot-cell">
        <button
          type="button"
          className={`wl-bot-dot${allowed ? ' is-on' : ''}`}
          aria-pressed={allowed}
          title={allowed ? WATCHLIST_BOT_ON_TITLE : WATCHLIST_BOT_OFF_TITLE}
          data-testid="watchlist-bot-toggle"
          onClick={(e) => {
            e.stopPropagation();
            onToggleBot(entry.symbol, !allowed);
          }}
        >
          {allowed ? '●' : '○'}
        </button>
      </td>
    </SelectableTableRow>
  );
}

interface Props {
  entries: WatchlistEntry[];
  loading: boolean;
  error: string | null;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}

export function WatchlistTable({ entries, loading, error, selectedSymbol, onSelectSymbol, onOpenTrading }: Props) {
  const [filter, setFilter] = useState<WatchlistFilter>('all');
  const stream = useSetupsBoard();
  const { isAllowed, add, remove } = useBotAllowlist();
  const setups = useMemo(() => setupsBySymbol(stream?.board?.rows), [stream?.board?.rows]);
  const following = Boolean(stream?.connected);
  const shown = useMemo(
    () => applyFilter(entries, filter, setups, isAllowed),
    [entries, filter, setups, isAllowed],
  );
  const sum = useMemo(() => summarize(entries, setups, isAllowed), [entries, setups, isAllowed]);
  const onToggleBot = (symbol: string, on: boolean) => void (on ? add(symbol) : remove(symbol));

  return (
    <div className="wl-table">
      <div className="wl-toolbar">
        <div className="wl-summary" data-testid="watchlist-summary">
          <span><b>{sum.total}</b> gappers &amp; gainers</span>
          <span><b>{sum.allPass}</b> pass all five pillars</span>
          <span><b>{sum.setupsLive}</b> setups live · <b>{sum.near}</b> near trigger</span>
          <span><b>{sum.allowlisted}</b> on the bot allowlist</span>
        </div>
        <div className="wl-filters" role="group" aria-label="Watchlist filter">
          {FILTERS.map(f => (
            <button
              key={f}
              type="button"
              className={`wl-fchip${filter === f ? ' is-on' : ''}`}
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {WATCHLIST_FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="empty-state">{error}</div>}
      {!error && shown.length === 0 ? (
        <div className="empty-state">
          {loading
            ? 'Loading watchlist…'
            : entries.length === 0
              ? 'No candidates currently meet scanning criteria.'
              : 'Nothing matches this filter.'}
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="wl-grid">
            <thead>
              <tr>
                <ScannerRowNumHeader />
                <th title="Click the row for the side panel. Click the ticker to open Trader.">Symbol</th>
                <th title="Price, % change, relative volume, news, float. Hover a letter for why it passed or failed.">Pillars</th>
                <th className="num">Last</th>
                <th className="num" title="Change against the prior close">% Chg</th>
                <th className="num" title="Volume today over the average daily volume">RVOL</th>
                <th className="num">Float</th>
                <th title="Today's catalyst since the prior close, by the same rules as the setup grade">News</th>
                <th title="0-100 composite: breaks ties among symbols with the same pillar count">Score</th>
                <th title="Where the first-pullback scanner has it">Setup</th>
                <th className="wl-bot-cell" title="On the bot allowlist">Bot</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((entry, index) => (
                <WatchlistRow
                  key={entry.symbol}
                  entry={entry}
                  index={index}
                  setup={setups.get(entry.symbol)}
                  following={following}
                  allowed={isAllowed(entry.symbol)}
                  onToggleBot={onToggleBot}
                  selected={selectedSymbol === entry.symbol}
                  onSelect={onSelectSymbol}
                  onOpenTrading={onOpenTrading}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="wl-footnote">{WATCHLIST_FOOTNOTE}</div>
    </div>
  );
}

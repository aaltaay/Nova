/** News Catalysts tab: on-roster names (IBKR Gappers / Gainers / AH) that also
 * have a recent headline, sorted by absolute gap magnitude. The full news
 * AI-in-trading desk lives on Nova News -- this table is not that product. */
import { Fragment, useState } from 'react';
import { SymbolSelectButton } from './SymbolSelectButton';
import { SelectableTableRow } from './SelectableTableRow';
import { ScannerRowNumCell, ScannerRowNumHeader } from './ScannerTable';
import { NewsCell } from './NewsCell';
import { NewsImpactPanel } from './NewsImpactPanel';
import { fmtPct, fmtVolume } from '../utils/quoteFormat';
import { NEWS_IMPACT_CLASS_LABELS, NEWS_IMPACT_CLASS_TOOLTIPS } from '../constants';
import type { Catalyst } from '../types/catalyst';
import type { SortConfig } from '../types/scanner';
import { catalystsEmptyCopy } from '../scanner/scannerHonesty';
import type { HealthStatus } from '../types/health';

const CATALYST_COLUMNS: [string, string][] = [
  ['symbol', 'Symbol'],
  ['previous_close', 'Prev Close'],
  ['current_price', 'Price'],
  ['gap_percent', 'Gap %'],
  ['volume', 'Volume'],
  ['catalyst_headline', 'Catalyst Headline'],
  ['newest_headline_at', 'News Time'],
];

interface CatalystsTableProps {
  catalysts: Catalyst[];
  sortState: SortConfig;
  onSort: (key: string) => void;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  health: HealthStatus;
  fetchError?: string | null;
}

export function CatalystsTable({
  catalysts, sortState, onSort, selectedSymbol, onSelect, onOpenTrading, health,
  fetchError = null,
}: CatalystsTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggleExpanded(symbol: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  }

  return (
    <>
      <div className="catalysts-description">
        On-roster news scanner -- names already on today's IBKR Gappers,
        Gainers, or After Hours lists that also have a recent headline.
        Open Nova News for AI-in-trading headlines.
      </div>
      {catalysts.length > 0 ? (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <ScannerRowNumHeader />
                {CATALYST_COLUMNS.map(([key, label]) => (
                  <th
                    key={key}
                    className="sortable-th"
                    onClick={() => onSort(key)}
                    aria-sort={
                      sortState.key === key
                        ? sortState.dir === 'asc' ? 'ascending' : 'descending'
                        : 'none'
                    }
                  >
                    <span className="th-inner">
                      {label}
                      <span className={`sort-arrow${sortState.key === key ? ' active' : ''}`}>
                        {sortState.key === key
                          ? sortState.dir === 'asc' ? '↑' : '↓'
                          : '↕'}
                      </span>
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {catalysts.map((c, index) => {
                const isExpanded = expanded.has(c.symbol);
                return (
                  <Fragment key={c.symbol}>
                    <SelectableTableRow
                      symbol={c.symbol}
                      selected={selectedSymbol === c.symbol}
                      onSelect={onSelect}
                      onOpenTrading={onOpenTrading}
                      openOnRowClick={false}
                    >
                      <ScannerRowNumCell index={index} />
                      <td>
                        <SymbolSelectButton
                          symbol={c.symbol}
                          exchange={c.exchange}
                          selected={selectedSymbol === c.symbol}
                          onSelect={onSelect}
                          onOpenTrading={onOpenTrading}
                        />
                      </td>
                      <td>${c.previous_close.toFixed(2)}</td>
                      <td>${c.current_price.toFixed(2)}</td>
                      <td className={c.gap_percent >= 0 ? 'positive' : 'negative'}>
                        {fmtPct(c.gap_percent)}
                      </td>
                      <td>{fmtVolume(c.volume)}</td>
                      <td className="catalyst-headline-cell">
                        <span className="catalyst-headline-text">
                          {c.catalyst_headline ? (
                            c.catalyst_url ? (
                              <a
                                href={c.catalyst_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="catalyst-headline-link"
                                title={c.catalyst_headline}
                                onClick={e => e.stopPropagation()}
                              >
                                {c.catalyst_headline.length > 80
                                  ? `${c.catalyst_headline.slice(0, 80)}…`
                                  : c.catalyst_headline}
                              </a>
                            ) : (
                              <span title={c.catalyst_headline}>
                                {c.catalyst_headline.length > 80
                                  ? `${c.catalyst_headline.slice(0, 80)}…`
                                  : c.catalyst_headline}
                              </span>
                            )
                          ) : (
                            <span className="na-muted">—</span>
                          )}
                        </span>
                        {c.catalyst_source && (
                          <span className="catalyst-source-tag">{c.catalyst_source}</span>
                        )}
                        {c.news_impact && (
                          <button
                            type="button"
                            className="ni-catalyst-badge"
                            aria-expanded={isExpanded}
                            title={
                              (NEWS_IMPACT_CLASS_TOOLTIPS[c.news_impact.impact_class] ?? '') +
                              '\n\n' +
                              (c.news_impact.reasons?.slice(0, 4).join('\n') ?? '')
                            }
                            onClick={e => {
                              e.stopPropagation();
                              toggleExpanded(c.symbol);
                            }}
                          >
                            {NEWS_IMPACT_CLASS_LABELS[c.news_impact.impact_class] ??
                              c.news_impact.impact_class}
                            {' · '}
                            {(c.news_impact.confidence * 100).toFixed(0)}%
                            {' · '}
                            {c.news_impact.sentiment}/{c.news_impact.lexicon_sentiment}
                            <span className="ni-catalyst-badge-caret">
                              {isExpanded ? '▲' : '▼'}
                            </span>
                          </button>
                        )}
                      </td>
                      <td><NewsCell newest_headline_at={c.newest_headline_at} /></td>
                    </SelectableTableRow>
                    {isExpanded && c.news_impact && (
                      <tr className="catalyst-expand-row">
                        <td colSpan={CATALYST_COLUMNS.length + 1}>
                          <NewsImpactPanel verdict={c.news_impact} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state">
          {catalystsEmptyCopy({
            fetchError,
            healthStatus: health.status,
            healthMessage: health.message,
          })}
        </div>
      )}
    </>
  );
}

/**
 * The Trader's News panel on the catalyst verdict (ADR 024): what the symbol's news since the prior
 * close actually is -- the catalyst, its source and age -- then the company items read, each
 * labelled, with movers lists and market wraps folded away. Replaces the rules-v1 impact read,
 * which judged whichever article was newest (a Dow market wrap scored "moved price 90%").
 */
import { useState } from 'react';
import {
  CATALYST_AGGREGATOR_SOURCES,
  CATALYST_NEWS_ALSO_NEGATIVE,
  CATALYST_NEWS_CHECKED_PREFIX,
  CATALYST_NEWS_PENDING_TITLE,
  CATALYST_NEWS_UNPLACED_NOTE,
  CATALYST_PANEL_HIDDEN_NOISE,
  CATALYST_PANEL_NO_COMPANY_ITEMS,
  CATALYST_PANEL_UNREAD,
  CATALYST_VERDICT_TITLES,
  NEWS_SECTION_DEFAULT_EXPANDED,
  NEWS_SECTION_TITLE,
} from '../constants';
import type { CatalystItem, CatalystPanel, CatalystVerdict } from '../types/catalystVerdict';
import { agoLabel, catalystHeadline, categoryLabel, sourceLabel } from '../utils/catalystVerdict';
import './catalystNews.css';

interface Props {
  panel: CatalystPanel | null;
  loading?: boolean;
  error?: string | null;
}

function verdictHeadline(v: CatalystVerdict | null): string {
  if (!v) return CATALYST_PANEL_UNREAD;
  if (v.verdict === 'catalyst' || v.verdict === 'negative') {
    const headline = catalystHeadline(v.title, v.source);
    return `${categoryLabel(v.category)}${headline ? `: ${headline}` : ''}`;
  }
  return CATALYST_VERDICT_TITLES[v.verdict] ?? v.verdict;
}

function itemMeta(item: CatalystItem, nowMs: number): string {
  const aggregated = !!item.source && CATALYST_AGGREGATOR_SOURCES.includes(item.source);
  const publisher = item.publisher && aggregated ? item.publisher : '';
  return [sourceLabel(item.source), publisher, agoLabel(item.published_ts, nowMs)].filter(Boolean).join(' · ');
}

function ItemRow({ item, nowMs }: { item: CatalystItem; nowMs: number }) {
  const headline = catalystHeadline(item.title, item.source) || categoryLabel(item.category);
  const tag = `${categoryLabel(item.category)}${item.strength ? ` (${item.strength})` : ''}`;
  return (
    <li className={`cn-item cn-item--${item.kind}`} data-kind={item.kind}>
      <span className="cn-item-tag">{tag}</span>
      {item.url ? (
        <a className="cn-item-headline" href={item.url} target="_blank" rel="noopener noreferrer" title={item.title ?? ''}>
          {headline}
        </a>
      ) : (
        <span className="cn-item-headline" title={item.title ?? ''}>{headline}</span>
      )}
      <span className="cn-item-meta">{itemMeta(item, nowMs)}</span>
    </li>
  );
}

function VerdictBlock({ v, nowMs }: { v: CatalystVerdict | null; nowMs: number }) {
  if (!v) return <div className="cn-verdict cn-verdict--unread">{CATALYST_PANEL_UNREAD}</div>;
  const placed = v.verdict === 'catalyst' || v.verdict === 'negative';
  const badge = placed
    ? `${CATALYST_VERDICT_TITLES[v.verdict]} · ${categoryLabel(v.category)}${v.strength ? ` (${v.strength})` : ''}`
    : CATALYST_VERDICT_TITLES[v.verdict] ?? v.verdict;
  const headline = placed ? catalystHeadline(v.title, v.source) : '';
  const meta = placed ? [sourceLabel(v.source), agoLabel(v.published_ts, nowMs)].filter(Boolean).join(' · ') : '';
  const checked = v.sources_answered?.length
    ? `${CATALYST_NEWS_CHECKED_PREFIX}: ${v.sources_answered.map(sourceLabel).join(', ')}`
      + (typeof v.n_items === 'number' ? ` · ${v.n_items} read` : '')
    : '';
  return (
    <div className={`cn-verdict cn-verdict--${v.verdict}`} data-verdict={v.verdict}>
      {v.news_pending && (
        <div className="cn-verdict-pending">{CATALYST_NEWS_PENDING_TITLE}{v.halt_code ? ` (${v.halt_code})` : ''}</div>
      )}
      <div className="cn-verdict-head">
        <span className="cn-verdict-badge">{badge}</span>
        {meta && <span className="cn-verdict-meta">{meta}</span>}
      </div>
      {headline && (v.url ? (
        <a className="cn-verdict-headline" href={v.url} target="_blank" rel="noopener noreferrer">{headline}</a>
      ) : (
        <p className="cn-verdict-headline">{headline}</p>
      ))}
      {v.verdict === 'catalyst' && v.category === 'company_news' && (
        <div className="cn-verdict-note">{CATALYST_NEWS_UNPLACED_NOTE}</div>
      )}
      {v.verdict === 'catalyst' && v.negative_too && <div className="cn-verdict-note cn-verdict-note--negative">{CATALYST_NEWS_ALSO_NEGATIVE}</div>}
      {checked && <div className="cn-verdict-checked">{checked}</div>}
    </div>
  );
}

export function CatalystNewsSection({ panel, loading = false, error = null }: Props) {
  const [expanded, setExpanded] = useState(NEWS_SECTION_DEFAULT_EXPANDED);
  const [showNoise, setShowNoise] = useState(false);
  const nowMs = Date.now();
  const v = panel?.verdict ?? null;
  const items = panel?.items ?? [];
  const company = items.filter((i) => i.kind !== 'noise');
  const noise = items.filter((i) => i.kind === 'noise');
  const preview = !panel && error ? error : verdictHeadline(v);
  const tone = v ? `cn-tone--${v.verdict}` : 'cn-tone--unread';

  return (
    <div
      className={`cq-news-section cn-section ${tone}${expanded ? ' cq-news-section--expanded' : ' cq-news-section--collapsed'}`}
      data-news-expanded={expanded ? 'true' : 'false'}
      data-news-source="catalyst"
    >
      <button
        type="button"
        className="cq-news-header cq-news-toggle"
        onClick={() => setExpanded((x) => !x)}
        aria-expanded={expanded}
        aria-controls="cq-news-body"
        title={expanded ? 'Collapse news' : 'Expand news'}
      >
        <span className="cq-news-toggle-left">
          <span className="cq-news-chevron" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
          <span className="cq-news-title">{NEWS_SECTION_TITLE}</span>
          {!expanded && (
            <span className="cq-news-preview cn-preview" title={preview}>
              {loading && !panel ? CATALYST_PANEL_UNREAD : preview}
            </span>
          )}
        </span>
        {company.length > 0 && <span className="cq-news-count">{company.length}</span>}
      </button>

      {expanded && (
        <div className="cq-news-body cn-body" id="cq-news-body">
          {error && <div className="cn-error" role="status">{error}</div>}
          <VerdictBlock v={v} nowMs={nowMs} />
          {panel && (company.length > 0 ? (
            <ul className="cn-items">
              {company.map((item, i) => <ItemRow key={item.item_id ?? i} item={item} nowMs={nowMs} />)}
            </ul>
          ) : (
            <div className="cn-empty">{CATALYST_PANEL_NO_COMPANY_ITEMS}</div>
          ))}
          {noise.length > 0 && (
            <div className="cn-noise">
              <button type="button" className="cn-noise-toggle" onClick={() => setShowNoise((x) => !x)} aria-expanded={showNoise}>
                {showNoise ? '▾' : '▸'} {noise.length} {CATALYST_PANEL_HIDDEN_NOISE}
              </button>
              {showNoise && (
                <ul className="cn-items cn-items--noise">
                  {noise.map((item, i) => <ItemRow key={item.item_id ?? i} item={item} nowMs={nowMs} />)}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

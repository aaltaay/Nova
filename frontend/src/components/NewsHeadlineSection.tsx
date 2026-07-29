import { useState } from 'react';
import {
  NEWS_FLAME_HOT_HOURS,
  NEWS_FLAME_MAX_HOURS,
  NEWS_FLAME_WARM_HOURS,
  NEWS_SECTION_DEFAULT_EXPANDED,
  NEWS_SECTION_TITLE,
} from '../constants';
import { NewsImpactPanel } from './NewsImpactPanel';
import type { NewsImpactVerdict } from '../types/newsImpact';

export interface NewsArticleRow {
  headline: string;
  summary?: string;
  author?: string;
  source?: string;
  url: string;
  created_at: string;
  symbols?: string[];
  images?: { url: string; size: string }[];
}

interface Props {
  news: NewsArticleRow[];
  newsImpact?: NewsImpactVerdict | null;
  timeAgo: (iso: string) => string;
  /** When false, skip the bump/impact panel (parent renders it elsewhere). */
  includeImpact?: boolean;
}

function previewHeadline(
  impact: NewsImpactVerdict | null,
  news: NewsArticleRow[],
): string {
  const fromImpact = impact?.headline?.trim();
  if (fromImpact) return fromImpact;
  return news[0]?.headline?.trim() ?? '';
}

/**
 * Ticker-detail news strip + explicit impact verdict (extracted from App.tsx).
 * One collapsible "News" container: collapsed by default with the lead headline
 * in the header; expanded shows impact factors + horizontal headline chips.
 */
export function NewsHeadlineSection({
  news,
  newsImpact,
  timeAgo,
  includeImpact = true,
}: Props) {
  const impact = includeImpact ? newsImpact : null;
  const [expanded, setExpanded] = useState(NEWS_SECTION_DEFAULT_EXPANDED);
  if (!news.length && !impact) return null;

  const headline = previewHeadline(impact ?? null, news);
  const count = news.length;

  return (
    <div
      className={`cq-news-section${expanded ? ' cq-news-section--expanded' : ' cq-news-section--collapsed'}`}
      data-news-expanded={expanded ? 'true' : 'false'}
    >
      <button
        type="button"
        className="cq-news-header cq-news-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls="cq-news-body"
        title={expanded ? 'Collapse news' : 'Expand news'}
      >
        <span className="cq-news-toggle-left">
          <span className="cq-news-chevron" aria-hidden="true">
            {expanded ? '▾' : '▸'}
          </span>
          <span className="cq-news-title">{NEWS_SECTION_TITLE}</span>
          {!expanded && headline && (
            <span className="cq-news-preview" title={headline}>
              {headline}
            </span>
          )}
        </span>
        {count > 0 && <span className="cq-news-count">{count}</span>}
      </button>

      {expanded && (
        <div className="cq-news-body" id="cq-news-body">
          {impact && <NewsImpactPanel verdict={impact} />}
          {news.length > 0 && (
            <div className="cq-news-list">
              {news.map((article, i) => {
                const ageHours =
                  (Date.now() - new Date(article.created_at).getTime()) / 3_600_000;
                const hasFlame = ageHours <= NEWS_FLAME_MAX_HOURS;
                const flameClass =
                  ageHours <= NEWS_FLAME_HOT_HOURS
                    ? 'flame-hot'
                    : ageHours <= NEWS_FLAME_WARM_HOURS
                      ? 'flame-warm'
                      : 'flame-cool';
                return (
                  <a
                    key={i}
                    className="cq-news-chip"
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={article.headline}
                  >
                    <span className="cq-news-chip-headline">{article.headline}</span>
                    <span className="cq-news-chip-meta">
                      {hasFlame && <span className={`cq-news-chip-flame ${flameClass}`} />}
                      {article.source && (
                        <span className="cq-news-source">{article.source}</span>
                      )}
                      <span className="cq-news-time">{timeAgo(article.created_at)}</span>
                    </span>
                  </a>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

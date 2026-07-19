import {
  NEWS_FLAME_HOT_HOURS,
  NEWS_FLAME_MAX_HOURS,
  NEWS_FLAME_WARM_HOURS,
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

/**
 * Ticker-detail news strip + explicit impact verdict (extracted from App.tsx).
 * Headlines render as a horizontally-scrolling row of clickable cards so every
 * title (and its source) stays visible without eating vertical space.
 */
export function NewsHeadlineSection({
  news,
  newsImpact,
  timeAgo,
  includeImpact = true,
}: Props) {
  const impact = includeImpact ? newsImpact : null;
  if (!news.length && !impact) return null;

  return (
    <div className="cq-news-section">
      {impact && <NewsImpactPanel verdict={impact} />}
      {news.length > 0 && (
        <>
          <div className="cq-news-header">
            <span className="cq-news-title">News Headline</span>
            <span className="cq-news-count">{news.length}</span>
          </div>
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
        </>
      )}
    </div>
  );
}

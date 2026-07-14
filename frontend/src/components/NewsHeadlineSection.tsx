import { useState } from 'react';
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
}

const NEWS_DEFAULT = 3;

/** Ticker-detail news list + explicit impact verdict (extracted from App.tsx). */
export function NewsHeadlineSection({ news, newsImpact, timeAgo }: Props) {
  const [newsExpanded, setNewsExpanded] = useState(false);
  if (!news.length && !newsImpact) return null;

  const visibleNews = newsExpanded ? news : news.slice(0, NEWS_DEFAULT);

  return (
    <div className="cq-news-section">
      {newsImpact && <NewsImpactPanel verdict={newsImpact} />}
      {news.length > 0 && (
        <>
          <div className="cq-news-header">
            <span className="cq-news-title">News Headline</span>
            {news.length > NEWS_DEFAULT && (
              <button className="cq-news-more" onClick={() => setNewsExpanded((x) => !x)}>
                {newsExpanded ? 'Less ▲' : 'More ▼'}
              </button>
            )}
          </div>
          <div className="cq-news-list">
            {visibleNews.map((article, i) => {
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
                <div key={i} className="cq-news-item">
                  <span
                    className={`cq-news-icon ${hasFlame ? `news-flame ${flameClass}` : 'cq-news-icon-blank'}`}
                  />
                  <span className="cq-news-main">
                    <a
                      className="cq-news-link"
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {article.headline}
                    </a>
                    {article.source && (
                      <span className="cq-news-source">{article.source}</span>
                    )}
                  </span>
                  <span className="cq-news-time">{timeAgo(article.created_at)}</span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

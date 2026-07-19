/** News headlines + impact for the open ticker. */
import { NewsHeadlineSection } from '../components/NewsHeadlineSection';
import type { TickerDetail } from '../types/ticker';
import { timeAgo } from '../utils/quoteFormat';

interface Props {
  detail: TickerDetail;
  /** Wrap in cq-news-row (columns layout). */
  wrapped?: boolean;
  /** When false, headlines only — bump/impact is rendered elsewhere. */
  includeImpact?: boolean;
}

export function NewsPanel({ detail, wrapped = false, includeImpact = true }: Props) {
  const news = detail.news ?? [];
  const impact = includeImpact ? detail.news_impact : null;
  const hasContent = news.length > 0 || !!impact;
  const body = (
    <div
      className="nova-module nova-module--news"
      data-module="news"
      data-news-count={String(news.length)}
      data-news-empty={hasContent ? 'false' : 'true'}
    >
      <NewsHeadlineSection
        news={news}
        newsImpact={detail.news_impact}
        timeAgo={timeAgo}
        includeImpact={includeImpact}
      />
    </div>
  );
  if (wrapped) {
    return <div className="cq-news-row">{body}</div>;
  }
  return body;
}

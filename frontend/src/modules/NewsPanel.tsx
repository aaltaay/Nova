/** News headlines + impact for the open ticker. */
import { CatalystNewsSection } from '../components/CatalystNewsSection';
import { NewsHeadlineSection } from '../components/NewsHeadlineSection';
import { WhyMovingSection } from '../components/WhyMovingSection';
import { useCatalystPanel } from '../hooks/useCatalystPanel';
import { useWhyMoving } from '../hooks/useWhyMoving';
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
  // The catalyst verdict (ADR 024) when this desk can read it; the sample desk and an API from
  // before the route keep the headline strip and its rules-v1 impact read.
  const catalyst = useCatalystPanel(detail.symbol);
  // Why it's moving (ADR 028): the rules read of the move, above the news that may or may not explain it.
  const why = useWhyMoving(detail.symbol);
  const news = detail.news ?? [];
  const impact = includeImpact ? detail.news_impact : null;
  const useVerdict = !catalyst.unavailable;
  const hasContent = useVerdict || !why.unavailable || news.length > 0 || !!impact;
  const body = (
    <div
      className="nova-module nova-module--news"
      data-module="news"
      data-news-count={String(useVerdict ? catalyst.panel?.items.length ?? 0 : news.length)}
      data-news-empty={hasContent ? 'false' : 'true'}
    >
      {!why.unavailable && (
        <WhyMovingSection key={`why-${detail.symbol}`} read={why.read} loading={why.loading} error={why.error} />
      )}
      {useVerdict ? (
        <CatalystNewsSection
          key={detail.symbol}
          panel={catalyst.panel}
          loading={catalyst.loading}
          error={catalyst.error}
        />
      ) : (
        <NewsHeadlineSection
          key={detail.symbol}
          news={news}
          newsImpact={detail.news_impact}
          timeAgo={timeAgo}
          includeImpact={includeImpact}
        />
      )}
    </div>
  );
  if (wrapped) {
    return <div className="cq-news-row">{body}</div>;
  }
  return body;
}

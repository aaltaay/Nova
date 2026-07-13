import type { NewsImpactVerdict } from './newsImpact';

/** One row of the experimental News Catalysts tab — any ticker mentioned in recent
 * market news, regardless of exchange/size (unlike the Gappers/Movers scanners). */
export interface Catalyst {
  symbol: string;
  previous_close: number;
  current_price: number;
  gap_percent: number;
  volume: number;
  has_news: boolean;
  newest_headline_at: string | null;
  catalyst_headline: string | null;
  catalyst_url: string | null;
  news_impact?: NewsImpactVerdict | null;
}

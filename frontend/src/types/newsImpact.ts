/** News impact verdict — mirrors backend/news/impact.py NewsImpactVerdict. */
export type NewsImpactClass =
  | 'moved_price'
  | 'attention_only'
  | 'no_effect'
  | 'insufficient_data';

export interface NewsImpactVerdict {
  symbol: string;
  impact_class: NewsImpactClass;
  confidence: number;
  age_hours: number | null;
  age_bucket: string;
  source_tier: string;
  source_name: string | null;
  confirmed_by_official: boolean;
  confirming_source_count: number;
  price_reaction: string;
  attention: string;
  l2_reaction: string;
  sentiment: string;
  sentiment_score: number | null;
  lexicon_sentiment: string;
  lexicon_polarity: number | null;
  headline: string | null;
  headline_url: string | null;
  summary: string;
  reasons: string[];
  factors: Record<string, unknown>;
  ai_reasoning: string | null;
  rule_version: string;
}

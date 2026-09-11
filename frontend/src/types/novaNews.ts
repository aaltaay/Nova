/** Nova News desk -- mirrors backend/nova_news/desk.py. Not a price feed. */

export type NovaNewsCriticality = 'critical' | 'high' | 'watch' | 'background';

export type NovaNewsFilter = 'all' | 'executes' | 'funds' | 'research' | 'small';

export type NovaNewsSource = {
  id: string;
  label: string;
  ok: boolean;
  count: number;
  error: string | null;
};

export type NovaNewsStory = {
  id: string;
  headline: string;
  summary: string;
  url: string;
  source: string;
  publisher: string;
  outlet_kind: string;
  criticality: NovaNewsCriticality;
  criticality_score: number;
  reasons: string[];
  symbols: string[];
  published_at: string | null;
  age_hours: number | null;
  provider: string;
  tags: string[];
};

export type NovaNewsDesk = {
  rev?: string;
  schema_version: number;
  as_of: number;
  error: string | null;
  sources: NovaNewsSource[];
  counts: Record<string, number>;
  columns: Record<NovaNewsCriticality, NovaNewsStory[]>;
  stories: NovaNewsStory[];
};

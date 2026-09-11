/** Feature-local tunables for the Nova News desk. */
import type { NovaNewsCriticality, NovaNewsFilter } from '../types/novaNews';

export const NOVA_NEWS_TITLE = 'Nova News';
export const NOVA_NEWS_TAGLINE =
  'The desk wire -- Yahoo, major outlets, and small publishers. Triage by criticality.';
export const NOVA_NEWS_POLL_MS = 60_000;
export const NOVA_NEWS_LEAD_COUNT = 3;
export const NOVA_NEWS_COLUMNS: readonly NovaNewsCriticality[] = [
  'critical',
  'high',
  'watch',
  'background',
];
export const NOVA_NEWS_COLUMN_LABELS: Record<NovaNewsCriticality, string> = {
  critical: 'Critical',
  high: 'High',
  watch: 'Watch',
  background: 'Background',
};
export const NOVA_NEWS_COLUMN_HINTS: Record<NovaNewsCriticality, string> = {
  critical: 'Official filings or language that can halt or reprice a name now.',
  high: 'Confirmed wires or small-publisher scoops that still move a desk.',
  watch: 'Fresh major coverage without a hard catalyst yet.',
  background: 'Context, recaps, and quieter small publishers -- still visible.',
};
export const NOVA_NEWS_FILTERS: readonly NovaNewsFilter[] = [
  'all',
  'markets',
  'filings',
  'yahoo',
  'small',
];
export const NOVA_NEWS_FILTER_LABELS: Record<NovaNewsFilter, string> = {
  all: 'All',
  markets: 'Markets',
  filings: 'Filings',
  yahoo: 'Yahoo',
  small: 'Small publishers',
};
export const NOVA_NEWS_SAMPLE_UNAVAILABLE =
  'Nova News sample desk is loading fixtures.';

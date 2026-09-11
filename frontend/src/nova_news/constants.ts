/** Feature-local tunables for the Nova News desk. */
import type { NovaNewsCriticality, NovaNewsFilter } from '../types/novaNews';

export const NOVA_NEWS_TITLE = 'Nova News';
export const NOVA_NEWS_TAGLINE =
  'AI used in trading -- desks, quants, bots, and research. Not AI stocks to buy.';
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
  critical: 'AI is placing or routing trades -- desks, algos, or enforcement.',
  high: 'Confirmed fund / execution coverage that still moves this beat.',
  watch: 'Headline pairs AI with trading, without a hard desk catalyst yet.',
  background: 'Research and quieter trade-press notes -- still on-topic.',
};
export const NOVA_NEWS_FILTERS: readonly NovaNewsFilter[] = [
  'all',
  'executes',
  'funds',
  'research',
  'small',
];
export const NOVA_NEWS_FILTER_LABELS: Record<NovaNewsFilter, string> = {
  all: 'All',
  executes: 'Executes',
  funds: 'Funds',
  research: 'Research',
  small: 'Small publishers',
};
export const NOVA_NEWS_SAMPLE_UNAVAILABLE =
  'Nova News sample desk is loading fixtures.';

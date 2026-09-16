/**
 * Low-signal movers / listicle headlines.
 * Keep in sync with backend/constants_archive_news.py NEWS_JUNK_*.
 */

export const NEWS_JUNK_HEADLINE_RES: readonly string[] = [
  String.raw`\b\d+\s+(?:\S+\s+){0,6}stocks?\s+moving\b`,
  String.raw`\bstocks?\s+moving\s+in\b.*\b(after[- ]?market|after[- ]?hours|pre[- ]?market|premarket|mid[- ]?day)\b`,
];

export const NEWS_JUNK_HEADLINE_PHRASES: readonly string[] = [
  'stocks to watch',
  'gainers and losers',
  'most active stocks',
  'movers recap',
  'biggest movers',
  'top movers',
  "today's movers",
  'todays movers',
  'premarket movers',
  'pre-market movers',
  'after-hours movers',
  'after hours movers',
  'after-market movers',
  'after market movers',
  'midday movers',
  'overnight movers',
];

export const NEWS_JUNK_SECTOR_ROUNDUP_RE = String.raw`\b(?:health\s*care|healthcare|biotech|technology|tech|energy|financial|banks?|retail|industrial|consumer|semiconductor|china|crypto|pharma)\s+stocks\s+(?:moving|to\s+watch|roundup|recap|in\s+focus)\b`;

export const NEWS_JUNK_URL_FRAGMENTS: readonly string[] = [
  '/trading-ideas/movers/',
  '/after-hours-movers',
  '/premarket-movers',
  '/pre-market-movers',
];

export const NEWS_SIGNAL_HEADLINE_KEYWORDS: readonly string[] = [
  'earnings',
  'fda',
  'sec filing',
  '8-k',
  '8k',
  '10-q',
  '10-k',
  'acquires',
  'acquired',
  'acquisition',
  'merger',
  'buyout',
  'offering',
  'bankruptcy',
  'guidance',
  'pdufa',
  'phase 3',
  'phase iii',
  'clinical trial',
  'press release',
];

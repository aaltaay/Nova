// Tunables for the homepage "AI in the markets" feed.
// Owner: site/api/ai-trading-news.mjs. No definitions elsewhere -- import from here.

/**
 * Google News RSS queries. Each one is fetched in parallel and merged.
 * `when:Nd` keeps Google from returning multi-year-old evergreen pages.
 * Measured yield (2026-09-11): ~224 raw items, ~125 publishers across these six.
 */
export const FEED_QUERIES = [
  '"AI trading" when:14d',
  '"algorithmic trading" AI when:14d',
  '"AI hedge fund" OR "quant fund" when:21d',
  '"AI agents" (investing OR trading OR markets) when:14d',
  '("machine learning" OR LLM) (traders OR "trading desk" OR "hedge fund") when:21d',
  'AI ("market making" OR "order execution" OR "trading desk") when:21d',
];

export const GOOGLE_NEWS_ENDPOINT = "https://news.google.com/rss/search";
export const GOOGLE_NEWS_LOCALE = { hl: "en-US", gl: "US", ceid: "US:en" };

/** A datacenter IP occasionally gets a slow response; fail that query, not the request. */
export const FETCH_TIMEOUT_MS = 6000;
export const USER_AGENT = "NovaSiteBot/1.0 (+https://nova.altaystudio.com)";

/** Items older than this never rank, regardless of source quality. */
export const MAX_ITEM_AGE_HOURS = 21 * 24;

/** Recency half-life. A 60h-old story keeps half the recency weight of a fresh one. */
export const RECENCY_HALF_LIFE_HOURS = 60;
export const RECENCY_WEIGHT = 4;

/** Minimum total score to be publishable. Tuned so off-topic allowlisted items drop out. */
export const MIN_SCORE = 4;

/** How many headlines the homepage shows, and the per-publisher cap that forces variety. */
export const MAX_ITEMS = 6;
export const MAX_PER_PUBLISHER = 2;

/**
 * Same-event merge threshold, on IDF-weighted title similarity.
 *
 * Measured on a live sample (2026-09-11) where six outlets covered one SEC
 * probe: genuine retellings scored 0.28-0.68 against each other, while the
 * closest unrelated pair (two different quant-fund stories) reached 0.148.
 * 0.25 sits in that gap. Going lower would collapse distinct stories, so a
 * loosely-worded retelling is allowed through rather than risk a false merge.
 */
export const DUPLICATE_TITLE_OVERLAP = 0.25;

/** Edge cache. The feed moves in hours, not seconds; serving stale beats serving nothing. */
export const CACHE_MAX_AGE_S = 900;
export const CACHE_STALE_WHILE_REVALIDATE_S = 3600;

/** Warm-lambda memory cache, so repeat hits inside one window skip Google entirely. */
export const MEMORY_CACHE_TTL_MS = CACHE_MAX_AGE_S * 1000;

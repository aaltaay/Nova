// GET /api/ai-trading-news
//
// Serves the homepage "AI in the markets" headlines. Runs server-side because
// Google News RSS is not CORS-readable from a browser and because the publisher
// allowlist should not be shipped to the client as a filter it could skip.
//
// Contract:
//   200 { status: "ok" | "degraded", items: [...], fetched_at, sources }
//   503 { status: "unavailable", items: [], error }
// The client renders an explicit failure state for 503. An empty list is never
// dressed up as a successful, fresh feed.

import {
  CACHE_MAX_AGE_S,
  CACHE_STALE_WHILE_REVALIDATE_S,
  FEED_QUERIES,
  FETCH_TIMEOUT_MS,
  GOOGLE_NEWS_ENDPOINT,
  GOOGLE_NEWS_LOCALE,
  MAX_ITEMS,
  MEMORY_CACHE_TTL_MS,
  USER_AGENT,
} from "./_lib/constants.mjs";
import { rankItems } from "./_lib/rank.mjs";
import { parseGoogleNewsRss } from "./_lib/rss.mjs";

/** Survives between warm invocations of the same lambda. */
let memoryCache = null;

function buildQueryUrl(query) {
  const url = new URL(GOOGLE_NEWS_ENDPOINT);
  url.searchParams.set("q", query);
  for (const [key, value] of Object.entries(GOOGLE_NEWS_LOCALE)) {
    url.searchParams.set(key, value);
  }
  return url.toString();
}

async function fetchQuery(query) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(buildQueryUrl(query), {
      signal: controller.signal,
      headers: { "user-agent": USER_AGENT, accept: "application/rss+xml, application/xml" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return parseGoogleNewsRss(await response.text());
  } finally {
    clearTimeout(timer);
  }
}

function toPayload(items, now, sourcesOk) {
  return {
    status: sourcesOk === FEED_QUERIES.length ? "ok" : "degraded",
    fetched_at: new Date(now).toISOString(),
    sources: { ok: sourcesOk, total: FEED_QUERIES.length },
    count: items.length,
    items: items.map((item) => ({
      title: item.title,
      url: item.link,
      publisher: item.publisher,
      host: item.host,
      tier: item.tier,
      published_at: item.publishedAt ? new Date(item.publishedAt).toISOString() : null,
    })),
  };
}

export default async function handler(request, response) {
  const now = Date.now();

  if (memoryCache && now - memoryCache.at < MEMORY_CACHE_TTL_MS) {
    response.setHeader("cache-control", `public, s-maxage=${CACHE_MAX_AGE_S}, stale-while-revalidate=${CACHE_STALE_WHILE_REVALIDATE_S}`);
    response.setHeader("x-nova-cache", "hit");
    return response.status(200).json(memoryCache.payload);
  }

  const settled = await Promise.allSettled(FEED_QUERIES.map(fetchQuery));
  const raw = settled.flatMap((result) => (result.status === "fulfilled" ? result.value : []));
  const sourcesOk = settled.filter((result) => result.status === "fulfilled").length;

  if (sourcesOk === 0) {
    response.setHeader("cache-control", "no-store");
    return response.status(503).json({
      status: "unavailable",
      items: [],
      error: "News source unreachable",
    });
  }

  const payload = toPayload(rankItems(raw, now, MAX_ITEMS), now, sourcesOk);
  memoryCache = { at: now, payload };

  response.setHeader("cache-control", `public, s-maxage=${CACHE_MAX_AGE_S}, stale-while-revalidate=${CACHE_STALE_WHILE_REVALIDATE_S}`);
  response.setHeader("x-nova-cache", "miss");
  return response.status(200).json(payload);
}

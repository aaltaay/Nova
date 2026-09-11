// Pure ranking pipeline: gate -> score -> dedupe -> diversify -> top N.
// No I/O here so the whole thing is unit testable against fixed headlines.

import {
  DUPLICATE_TITLE_OVERLAP,
  MAX_ITEMS,
  MAX_ITEM_AGE_HOURS,
  MAX_PER_PUBLISHER,
  MIN_SCORE,
  RECENCY_HALF_LIFE_HOURS,
  RECENCY_WEIGHT,
} from "./constants.mjs";
import {
  AI_TERMS,
  MARKET_TERMS,
  PROMO_PATTERNS,
  PROMO_PENALTY,
  SECTOR_NOISE,
  SECTOR_NOISE_PENALTY,
  SIGNAL_PHRASES,
  SPAM_PATTERNS,
} from "./lexicon.mjs";
import { lookupPublisher, normalizeHost } from "./publishers.mjs";

/** Lowercase, collapse punctuation to spaces, keep "a.i." style dots intact. */
function normalizeText(value) {
  return ` ${String(value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9.\-\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim()} `;
}

/** Whole-token match so "ai" does not fire inside "said" or "chain". */
function hasTerm(haystack, term) {
  const padded = ` ${term} `;
  if (haystack.includes(padded)) return true;
  // Allow a trailing possessive/plural boundary for multi-word phrases.
  return haystack.includes(`${padded.trimEnd()}s `);
}

export function matchesAny(text, terms) {
  const haystack = normalizeText(text);
  return terms.some((term) => hasTerm(haystack, term));
}

export function isSpam(title) {
  const haystack = normalizeText(title);
  return SPAM_PATTERNS.some((pattern) => pattern.test(haystack));
}

function signalScore(haystack) {
  let total = 0;
  let hits = 0;
  for (const [phrase, weight] of SIGNAL_PHRASES) {
    if (hasTerm(haystack, phrase)) {
      total += weight;
      hits += 1;
    }
  }
  // Two independent signals is much stronger evidence than one repeated idea,
  // but do not let a keyword-stuffed headline run away with the ranking.
  return { score: Math.min(total, 12), hits };
}

function noiseScore(haystack) {
  return SECTOR_NOISE.filter((term) => hasTerm(haystack, term)).length;
}

export function recencyScore(publishedAt, now) {
  if (!publishedAt) return 0;
  const ageHours = (now - publishedAt) / 3_600_000;
  if (ageHours < 0) return RECENCY_WEIGHT;
  return RECENCY_WEIGHT * Math.pow(0.5, ageHours / RECENCY_HALF_LIFE_HOURS);
}

/**
 * Score one parsed item. Returns null when the item must never be published.
 * Rejection reasons are kept on the returned object for debugging via ?debug=1.
 */
export function scoreItem(item, now = Date.now()) {
  const publisher = lookupPublisher(item.sourceUrl);
  if (!publisher) return null;

  const ageHours = item.publishedAt ? (now - item.publishedAt) / 3_600_000 : null;
  if (ageHours !== null && ageHours > MAX_ITEM_AGE_HOURS) return null;

  if (isSpam(item.title)) return null;

  const haystack = normalizeText(item.title);
  if (!AI_TERMS.some((term) => hasTerm(haystack, term))) return null;
  if (!MARKET_TERMS.some((term) => hasTerm(haystack, term))) return null;

  const signal = signalScore(haystack);
  const noise = noiseScore(haystack);
  // An AI-sector story with no trading signal is a stock story, not this feed.
  if (noise > 0 && signal.hits === 0) return null;

  const promo = PROMO_PATTERNS.some((pattern) => pattern.test(haystack)) ? PROMO_PENALTY : 0;

  const score =
    publisher.weight +
    signal.score +
    recencyScore(item.publishedAt, now) -
    noise * SECTOR_NOISE_PENALTY -
    promo;

  if (score < MIN_SCORE) return null;

  return {
    ...item,
    host: normalizeHost(item.sourceUrl),
    // Prefer the curated name: Google reports Barron's as the string "barrons.com".
    publisher: publisher.name,
    tier: publisher.tier,
    score: Math.round(score * 100) / 100,
  };
}

const STOP_WORDS = new Set([
  "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
  "are", "as", "at", "by", "from", "its", "it", "that", "this", "how", "why",
  "new", "says", "said", "has", "have", "will", "be", "over", "into", "his",
  "her", "their", "they", "he", "she", "now",
]);

/** Dots are dropped here so the NYT's "S.E.C." clusters with everyone else's "SEC". */
export function titleTokens(title) {
  return new Set(
    normalizeText(title)
      .split(" ")
      .map((word) => word.replace(/\./g, ""))
      .filter((word) => word.length > 2 && !STOP_WORDS.has(word)),
  );
}

/**
 * Inverse document frequency across the candidate set.
 *
 * This is what makes same-event detection work here. Every headline in this
 * feed contains "ai", "fund" or "trading", so plain word overlap rates all of
 * them as mildly similar and none as duplicates. Weighting by rarity means the
 * shared word "subpoenas" counts and the shared word "ai" does not.
 */
export function buildIdf(titles) {
  const documentFrequency = new Map();
  for (const title of titles) {
    for (const token of titleTokens(title)) {
      documentFrequency.set(token, (documentFrequency.get(token) ?? 0) + 1);
    }
  }
  const total = titles.length;
  const idf = new Map();
  for (const [token, frequency] of documentFrequency) {
    idf.set(token, Math.max(0, Math.log(total / frequency)));
  }
  return idf;
}

function weightOf(tokens, idf) {
  let sum = 0;
  for (const token of tokens) sum += idf.get(token) ?? 0;
  return sum;
}

/** Share of the lighter headline's distinctive weight that the two have in common. */
export function titleOverlap(a, b, idf) {
  const left = titleTokens(a);
  const right = titleTokens(b);
  const leftWeight = weightOf(left, idf);
  const rightWeight = weightOf(right, idf);
  if (leftWeight === 0 || rightWeight === 0) return 0;
  let shared = 0;
  for (const token of left) if (right.has(token)) shared += idf.get(token) ?? 0;
  return shared / Math.min(leftWeight, rightWeight);
}

/**
 * Collapse each news event to its single highest-scoring telling, so six slots
 * hold six stories rather than six versions of one.
 */
export function dedupe(items) {
  const idf = buildIdf(items.map((item) => item.title));
  const kept = [];
  for (const item of [...items].sort((a, b) => b.score - a.score)) {
    const duplicate = kept.some(
      (other) =>
        other.link === item.link ||
        titleOverlap(other.title, item.title, idf) >= DUPLICATE_TITLE_OVERLAP,
    );
    if (!duplicate) kept.push(item);
  }
  return kept;
}

/** Cap per publisher so one outlet cannot own the whole list. */
export function diversify(items, limit = MAX_ITEMS, perPublisher = MAX_PER_PUBLISHER) {
  const counts = new Map();
  const picked = [];
  for (const item of items) {
    const used = counts.get(item.host) ?? 0;
    if (used >= perPublisher) continue;
    counts.set(item.host, used + 1);
    picked.push(item);
    if (picked.length >= limit) break;
  }
  return picked;
}

/** Full pipeline over raw parsed RSS items. */
export function rankItems(rawItems, now = Date.now(), limit = MAX_ITEMS) {
  const scored = [];
  for (const item of rawItems) {
    const result = scoreItem(item, now);
    if (result) scored.push(result);
  }
  return diversify(dedupe(scored), limit);
}

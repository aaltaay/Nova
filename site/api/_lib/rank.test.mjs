import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_ITEM_AGE_HOURS, RECENCY_HALF_LIFE_HOURS, RECENCY_WEIGHT } from "./constants.mjs";
import { buildIdf, dedupe, diversify, isSpam, rankItems, recencyScore, scoreItem, titleOverlap } from "./rank.mjs";

const NOW = Date.parse("2026-09-11T00:00:00Z");
const HOUR = 3_600_000;

function item(title, sourceUrl, ageHours = 4, extra = {}) {
  return {
    title,
    link: `https://news.google.com/${encodeURIComponent(title).slice(0, 40)}`,
    sourceUrl,
    publisherName: sourceUrl,
    publishedAt: NOW - ageHours * HOUR,
    ...extra,
  };
}

test("accepts a genuine AI-trading story from an allowlisted publisher", () => {
  const scored = scoreItem(
    item("Inside Bracket22, a trading firm powered by AI agents", "https://www.cnbc.com"),
    NOW,
  );
  assert.ok(scored, "expected the story to rank");
  assert.equal(scored.host, "cnbc.com");
  assert.equal(scored.tier, "major");
  assert.ok(scored.score > 8, `expected a strong score, got ${scored.score}`);
});

test("uses the curated publisher name, not Google's inconsistent source text", () => {
  // Google reports this publisher as the bare string "barrons.com".
  const raw = item("Quant fund rebuilds its trading algorithm around LLMs", "https://www.barrons.com");
  raw.publisherName = "barrons.com";
  assert.equal(scoreItem(raw, NOW).publisher, "Barron's");
});

test("rejects every publisher outside the allowlist, however good the headline", () => {
  const headline = "Inside Bracket22, a trading firm powered by AI agents";
  assert.equal(scoreItem(item(headline, "https://thearabtribune.com"), NOW), null);
  assert.equal(scoreItem(item(headline, "https://www.prnewswire.com"), NOW), null);
});

test("rejects press-release subdomains of otherwise trusted publishers", () => {
  // businessinsider.com is real reporting; markets.businessinsider.com is a PR pipe.
  assert.ok(scoreItem(item("How AI reshaped a hedge fund trading desk", "https://www.businessinsider.com"), NOW));
  assert.equal(
    scoreItem(item("How AI reshaped a hedge fund trading desk", "https://markets.businessinsider.com"), NOW),
    null,
  );
});

test("rejects the spam shapes observed in the live feed", () => {
  const spam = [
    "AI Trading Forex (ATF) Expands Across TON With 80,000+ Holders as Telegram Mini App Launches",
    "5 Best AI Trading Bot Platforms in 2026: How Traders Use AI Bots",
    "MoneySimpler Launches Retirement Income System, AI Trading Offers Retiree $7,700 Potential Profit",
    "BGC Looks 5.7% Undervalued on GF Value as AI Trading Boosts Growth",
    "AI Trading Engine Review My Real Test With Results & Demo.png",
    "Market-Making Transactions Disclosed for Oyak Yatirim Ortakligi Shares",
    "Pelican AI Corp. Receives Final CSE Approval and Announces Commencement of Trading Under Symbol",
  ];
  for (const title of spam) {
    assert.ok(isSpam(title), `expected spam: ${title}`);
    assert.equal(scoreItem(item(title, "https://www.cnbc.com"), NOW), null, `leaked: ${title}`);
  }
});

test("rejects AI-as-a-sector stories that carry no trading signal", () => {
  assert.equal(
    scoreItem(item("Nvidia earnings beat lifts AI stocks as chip demand surges", "https://www.cnbc.com"), NOW),
    null,
  );
  assert.equal(
    scoreItem(item("AI bubble fears drag markets lower on data center capex", "https://www.reuters.com"), NOW),
    null,
  );
});

test("keeps a trading story that merely mentions the AI sector", () => {
  const scored = scoreItem(
    item("Nvidia-owning quant fund rebuilds its trading algorithm around LLMs", "https://www.reuters.com"),
    NOW,
  );
  assert.ok(scored, "sector words should penalise, not veto, when trading signal is present");
});

test("requires both an AI term and a market term", () => {
  assert.equal(scoreItem(item("Hedge fund manager raises a new macro fund", "https://www.reuters.com"), NOW), null);
  assert.equal(scoreItem(item("OpenAI releases a faster language model", "https://www.reuters.com"), NOW), null);
});

test("does not match 'ai' inside unrelated words", () => {
  // "said" / "chain" contain the letters but must not satisfy the AI gate.
  assert.equal(scoreItem(item("Trader said the supply chain hurt equities", "https://www.reuters.com"), NOW), null);
});

test("drops items older than the hard window", () => {
  const title = "Inside Bracket22, a trading firm powered by AI agents";
  assert.ok(scoreItem(item(title, "https://www.cnbc.com", MAX_ITEM_AGE_HOURS - 1), NOW));
  assert.equal(scoreItem(item(title, "https://www.cnbc.com", MAX_ITEM_AGE_HOURS + 1), NOW), null);
});

test("recency decays by half over one half-life", () => {
  assert.equal(recencyScore(NOW, NOW), RECENCY_WEIGHT);
  const halved = recencyScore(NOW - RECENCY_HALF_LIFE_HOURS * HOUR, NOW);
  assert.ok(Math.abs(halved - RECENCY_WEIGHT / 2) < 1e-9);
  assert.equal(recencyScore(null, NOW), 0);
});

/**
 * A verbatim capture of everything that survived scoring on 2026-09-11, in
 * score order. IDF is corpus-relative, so dedupe must be exercised against a
 * production-sized candidate set -- a handful of headlines produces different
 * weights and would not reproduce the behaviour the threshold was tuned for.
 * Entries 0-3, 6 and 11 are six outlets covering one SEC probe.
 */
const LIVE_CORPUS = [
  ["Goldman Sachs, Citi, JPMorgan Face Subpoenas Over AI Hedge Fund: Reports", "barrons.com", 13.04],
  ["SEC reportedly subpoenas Wall Street banks over AI hedge fund Situational Awareness's near collapse", "cnbc.com", 11.54],
  ["SEC subpoenaed Wall Street banks over AI hedge fund Situational Awareness's near-collapse", "qz.com", 11.54],
  ["Situational Awareness, star AI hedge fund that nearly imploded, now being probed by the SEC", "techcrunch.com", 11.53],
  ["Billionaire hedge fund investor Paul Tudor Jones says AI is like a 'Category 6 hurricane' heading for humanity", "businessinsider.com", 10.1],
  ["Tech roundup: Questrade offers direct links for agentic AI trading agent", "investmentexecutive.com", 9.38],
  ["S.E.C. Investigating Near-Implosion of A.I. Hedge Fund", "nytimes.com", 8.03],
  ["How AI and the hedge fund talent war pushed Man Group to reimagine its $156 billion quant empire", "businessinsider.com", 7.91],
  ["NinjaTrader Brings AI and MCP to Retail Futures Trading", "financemagnates.com", 6.7],
  ["MetaTrader 5 AI Assistant Becomes a QA Engineer for Trading Bots", "financemagnates.com", 6.54],
  ["DeepSeek looks for fresh capital as founder's quant empire navigates China's choppy IPO market", "cnbc.com", 4.57],
  ["US investigates trades made by 'golden child' of AI's hedge fund", "finance.yahoo.com", 4.54],
  ["How Crypto Trading Is Changing With Zero Fees and AI", "finance.yahoo.com", 4.05],
].map(([title, host, score], index) => ({ title, host, score, link: `https://example.test/${index}` }));

const titleAt = (index) => LIVE_CORPUS[index].title;

test("IDF weighting rates same-event retellings above unrelated quant stories", () => {
  const idf = buildIdf(LIVE_CORPUS.map((entry) => entry.title));
  const sameEvent = titleOverlap(titleAt(1), titleAt(6), idf);
  // Two different quant-fund stories: the closest unrelated pair in this sample.
  const unrelated = titleOverlap(titleAt(7), titleAt(10), idf);
  assert.ok(sameEvent > unrelated, `same-event ${sameEvent} should beat unrelated ${unrelated}`);
  assert.ok(unrelated < 0.25, `unrelated pair ${unrelated} must stay under the merge threshold`);
});

test("dedupe collapses retellings of one event and keeps every distinct story", () => {
  const kept = dedupe(LIVE_CORPUS);
  const keptTitles = new Set(kept.map((entry) => entry.title));

  for (const index of [2, 3, 6]) {
    assert.ok(!keptTitles.has(titleAt(index)), `expected retelling dropped: ${titleAt(index)}`);
  }
  // Every story that is genuinely its own event stays.
  for (const index of [4, 5, 7, 8, 9, 10, 12]) {
    assert.ok(keptTitles.has(titleAt(index)), `expected distinct story kept: ${titleAt(index)}`);
  }
  assert.equal(kept[0].title, titleAt(0), "highest score leads");
  assert.equal(kept.length, 10);
});

test("the six-slot homepage list never repeats a publisher more than twice", () => {
  const shown = diversify(dedupe(LIVE_CORPUS));
  const counts = new Map();
  for (const entry of shown) counts.set(entry.host, (counts.get(entry.host) ?? 0) + 1);
  assert.equal(shown.length, 6);
  assert.ok(Math.max(...counts.values()) <= 2);
});

test("dedupe treats an identical link as the same story", () => {
  const kept = dedupe([
    { title: "Totally different words here", link: "https://a.test/1", host: "a.test", score: 5 },
    { title: "Nothing alike whatsoever friend", link: "https://a.test/1", host: "b.test", score: 4 },
  ]);
  assert.equal(kept.length, 1);
});

test("diversify caps a single publisher and honours the limit", () => {
  const items = Array.from({ length: 6 }, (_, index) => ({
    title: `Story ${index}`,
    host: index < 4 ? "cnbc.com" : "reuters.com",
    score: 10 - index,
  }));
  const picked = diversify(items, 6, 2);
  assert.equal(picked.filter((entry) => entry.host === "cnbc.com").length, 2);
  assert.equal(picked.length, 4);
  assert.equal(diversify(items, 1, 2).length, 1);
});

test("rankItems runs the whole pipeline and returns publishable stories only", () => {
  const raw = [
    item("Inside Bracket22, a trading firm powered by AI agents", "https://www.cnbc.com", 2),
    item("AI Trading Forex (ATF) Expands Across TON With 80,000+ Holders", "https://www.cnbc.com", 2),
    item("Nvidia earnings beat lifts AI stocks on chip demand", "https://www.reuters.com", 2),
    item("Quant fund rebuilds its trading algorithm around reinforcement learning", "https://www.ft.com", 3),
    item("Best 5 AI trading bots for beginners", "https://thearabtribune.com", 1),
  ];
  const ranked = rankItems(raw, NOW);
  assert.deepEqual(
    ranked.map((entry) => entry.host),
    ["ft.com", "cnbc.com"],
    "only the two legitimate stories survive, best score first",
  );
});

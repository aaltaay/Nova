// Topical vocabulary for "AI is used to trade".
//
// The distinction this file exists to enforce: AI as the *tool doing the
// trading* (quant funds, execution algorithms, agentic portfolios) is on topic.
// AI as the *sector being traded* (chip demand, AI capex, an AI-led rally) is
// not, even though both match the words "AI" and "market".

/** Both gates must hit, or the item is rejected before scoring. */
export const AI_TERMS = [
  "ai",
  "a.i.",
  "artificial intelligence",
  "machine learning",
  "deep learning",
  "neural network",
  "llm",
  "large language model",
  "gpt",
  "chatgpt",
  "agentic",
  "ai agent",
  "algorithm",
  "quant",
  "automated",
];

export const MARKET_TERMS = [
  "trading",
  "trader",
  "trades",
  "hedge fund",
  "market",
  "markets",
  "investing",
  "investor",
  "portfolio",
  "stocks",
  "equities",
  "securities",
  "broker",
  "exchange",
  "wall street",
  "asset manager",
  "execution",
  "sec",
  "regulator",
];

/**
 * Phrases that mean the story really is about AI operating in a market.
 * Weighted: a headline can accumulate several.
 */
export const SIGNAL_PHRASES = [
  ["ai hedge fund", 5],
  ["ai-powered trading", 5],
  ["ai powered trading", 5],
  ["algorithmic trading", 5],
  ["algo trading", 4],
  ["quant fund", 5],
  ["quantitative trading", 5],
  ["trading algorithm", 5],
  ["ai trading", 4],
  ["agentic trading", 5],
  ["ai agents invest", 5],
  ["ai trader", 4],
  ["trading desk", 3],
  ["market making", 4],
  ["high-frequency trading", 4],
  ["order execution", 4],
  ["execution algorithm", 4],
  ["systematic strategy", 4],
  ["systematic trading", 4],
  ["reinforcement learning", 3],
  ["machine learning model", 3],
  ["portfolio manager", 3],
  ["robo-adviser", 3],
  ["robo-advisor", 3],
  ["trading bot", 2],
  ["backtest", 2],
  ["alpha", 1],
  ["hedge fund", 2],
  ["prop trading", 3],
  ["proprietary trading", 3],
];

/**
 * AI-as-a-sector vocabulary. Penalized, and fatal when the headline carries no
 * signal phrase at all -- that combination is a stock story wearing AI words.
 */
export const SECTOR_NOISE = [
  "ai stocks",
  "ai bubble",
  "ai rally",
  "ai capex",
  "ai spending",
  "ai infrastructure",
  "data center",
  "datacenter",
  "semiconductor",
  "chipmaker",
  "chip demand",
  "nvidia",
  "magnificent seven",
  "earnings beat",
  "price target",
  "market cap",
];

export const SECTOR_NOISE_PENALTY = 3;

/**
 * Hard rejects. Every pattern here was observed in a live sample of the same
 * queries: crypto shilling, affiliate listicles, retiree-income spam, exchange
 * filing boilerplate, and raw image filenames used as headlines.
 */
export const SPAM_PATTERNS = [
  /\bpresale\b/,
  /\bmeme ?coin\b/,
  /\bairdrop\b/,
  /\bwhales?\b/,
  /\bholders\b/,
  /\bmini app\b/,
  /\bprice prediction\b/,
  /\bbull run\b/,
  /\b\d+x\b/,
  /\b(best|top)\s+\d+\b/,
  /\b\d+\s+(best|top)\b/,
  /\breview\b/,
  /\bhow to make money\b/,
  /\bfor beginners\b/,
  /\bstep[-\s]by[-\s]step\b/,
  /\bsponsored\b/,
  /\bpromo code\b/,
  /\bpassive income\b/,
  /\bboost income\b/,
  /\bpotential (income|profit|payout)\b/,
  /\$[\d,]+\s*(potential|profit|payout|daily|monthly)\b/,
  /\bundervalued\b/,
  /\bstocks? to (buy|watch)\b/,
  /\bbuy or sell\b/,
  /\bgf value\b/,
  /\bmarket-making transactions disclosed\b/,
  /\bliquidity-providing trades\b/,
  /\bcommencement of trading under (the )?symbol\b/,
  /\breceives final .{0,24}approval\b/,
  /\.(png|jpe?g|webp)\b/,
];

/**
 * Promotional launch grammar. Not fatal on its own -- a real vendor story like
 * "NinjaTrader Brings AI and MCP to Retail Futures Trading" uses it -- so this
 * only shades the score.
 */
export const PROMO_PATTERNS = [
  /\b(launches|unveils|introduces|debuts|rolls out|expands|announces)\b/,
  /\bmarks \w+ years?\b/,
  /\bpartners with\b/,
  /\bachieves\b/,
];

export const PROMO_PENALTY = 2;

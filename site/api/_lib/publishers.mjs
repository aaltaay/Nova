// Publisher allowlist -- the primary quality lever for this feed.
//
// Why an allowlist and not a blocklist: a raw Google News query for "AI trading"
// is dominated by crypto-affiliate sites, press-release wires, and SEO content
// farms. Measured on 2026-09-11, the ten most frequent publishers were almost
// entirely those; WSJ, NYT, Reuters and CNBC each appeared once or twice in the
// long tail. Blocking bad domains is unwinnable -- the supply is infinite.
//
// Hosts are matched EXACTLY (after stripping a leading "www."). That is
// deliberate: `businessinsider.com` is real reporting while
// `markets.businessinsider.com` is a press-release pipe that published
// "MoneySimpler Launches AI Trading App" during the same sample. Registrable-
// domain matching would let that back in.
//
// Each entry carries its own display name because Google's <source> text is
// inconsistent -- it reports Barron's as the bare string "barrons.com".
//
// To add a publisher: put [host, display name] in the tier that matches its
// editorial standard. Nothing outside this map is ever shown.

/** Wire-grade financial and general reporting. */
const TIER_PRIMARY = [
  ["wsj.com", "The Wall Street Journal"],
  ["bloomberg.com", "Bloomberg"],
  ["reuters.com", "Reuters"],
  ["ft.com", "Financial Times"],
  ["nytimes.com", "The New York Times"],
  ["economist.com", "The Economist"],
  ["barrons.com", "Barron's"],
  ["theinformation.com", "The Information"],
];

/** Strong national desks and technology press. */
const TIER_MAJOR = [
  ["cnbc.com", "CNBC"],
  ["marketwatch.com", "MarketWatch"],
  ["businessinsider.com", "Business Insider"],
  ["fortune.com", "Fortune"],
  ["axios.com", "Axios"],
  ["apnews.com", "AP News"],
  ["theguardian.com", "The Guardian"],
  ["washingtonpost.com", "The Washington Post"],
  ["semafor.com", "Semafor"],
  ["qz.com", "Quartz"],
  ["technologyreview.com", "MIT Technology Review"],
  ["wired.com", "Wired"],
  ["arstechnica.com", "Ars Technica"],
  ["theverge.com", "The Verge"],
  ["techcrunch.com", "TechCrunch"],
  ["spectrum.ieee.org", "IEEE Spectrum"],
  ["nature.com", "Nature"],
  ["science.org", "Science"],
  ["npr.org", "NPR"],
  ["bbc.com", "BBC"],
  ["cnn.com", "CNN"],
];

/** Trade press. Lower reach, highest topical density for how desks actually run. */
const TIER_TRADE = [
  ["risk.net", "Risk.net"],
  ["waterstechnology.com", "WatersTechnology"],
  ["thetradenews.com", "The TRADE"],
  ["institutionalinvestor.com", "Institutional Investor"],
  ["pionline.com", "Pensions & Investments"],
  ["hedgeweek.com", "Hedgeweek"],
  ["fnlondon.com", "Financial News London"],
  ["efinancialcareers.com", "eFinancialCareers"],
  ["financemagnates.com", "Finance Magnates"],
  ["americanbanker.com", "American Banker"],
  ["bankingdive.com", "Banking Dive"],
  ["tradersmagazine.com", "Traders Magazine"],
  ["globalcustodian.com", "Global Custodian"],
  ["thebanker.com", "The Banker"],
  ["investmentexecutive.com", "Investment Executive"],
  ["citywire.com", "Citywire"],
  ["advisorhub.com", "AdvisorHub"],
  ["coindesk.com", "CoinDesk"],
];

/** Useful but syndication-heavy. Needs a strong topical score to survive MIN_SCORE. */
const TIER_SECONDARY = [
  ["finance.yahoo.com", "Yahoo Finance"],
  ["theregister.com", "The Register"],
  ["venturebeat.com", "VentureBeat"],
  ["scmp.com", "South China Morning Post"],
  ["asia.nikkei.com", "Nikkei Asia"],
  ["investopedia.com", "Investopedia"],
  ["forbes.com", "Forbes"],
  ["fastcompany.com", "Fast Company"],
  ["inc.com", "Inc."],
];

const TIERS = [
  [TIER_PRIMARY, 6, "primary"],
  [TIER_MAJOR, 4.5, "major"],
  [TIER_TRADE, 4, "trade"],
  [TIER_SECONDARY, 2.5, "secondary"],
];

/** host -> { name, weight, tier } */
export const PUBLISHERS = new Map(
  TIERS.flatMap(([entries, weight, tier]) =>
    entries.map(([host, name]) => [host, { name, weight, tier }]),
  ),
);

/** Strip protocol, credentials, "www." and any path so a `<source url>` becomes a bare host. */
export function normalizeHost(value) {
  if (!value) return "";
  let host = String(value).trim().toLowerCase();
  host = host.replace(/^[a-z]+:\/\//, "");
  host = host.split("/")[0].split("@").pop() ?? "";
  host = host.split(":")[0];
  return host.replace(/^www\./, "");
}

/** Returns { name, weight, tier } for an allowlisted host, or null. */
export function lookupPublisher(hostOrUrl) {
  return PUBLISHERS.get(normalizeHost(hostOrUrl)) ?? null;
}

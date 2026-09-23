/** Catalyst verdicts on the desk (ADR 024). The backend owns the rules (`backend/constants_catalysts.py`). */

/** Catalyst classes (backend ``constants_catalysts``) as the desk names them. */
export const CATALYST_CATEGORY_LABELS: Record<string, string> = {
  fda_regulatory: 'FDA / regulatory',
  clinical_data: 'Clinical data',
  merger_acquisition: 'Merger / acquisition',
  contract_partnership: 'Contract / partnership',
  earnings_guidance: 'Earnings / guidance',
  listing_financing: 'Listing / financing',
  theme_pivot: 'Theme pivot (AI, crypto ...)',
  product_news: 'Product news',
  company_news: 'Company news',
  offering_dilution: 'Offering / dilution',
  delisting_split: 'Delisting / reverse split',
  corporate_routine: 'Routine company item',
  periodic_report: 'Periodic report',
  presentation: 'Investor presentation',
  merger_paperwork: 'Merger paperwork',
  listing_paperwork: 'Listing paperwork',
  filing_other: 'Other filing',
  movers_list: 'Movers list',
  law_firm: 'Law-firm advert',
  opinion: 'Opinion piece',
  roundup: 'Multi-stock roundup',
  halt_notice: 'Halt notice',
  analyst_action: 'Analyst note',
  empty: 'No headline',
};

/** The Watchlist's News column: a catalyst class in a word (full names: CATALYST_CATEGORY_LABELS). */
export const CATALYST_CATEGORY_SHORT: Record<string, string> = {
  fda_regulatory: 'FDA',
  clinical_data: 'Clinical',
  merger_acquisition: 'M&A',
  contract_partnership: 'Contract',
  earnings_guidance: 'Earnings',
  listing_financing: 'Financing',
  theme_pivot: 'Theme',
  product_news: 'Product',
  company_news: 'News',
  offering_dilution: 'Dilution',
  delisting_split: 'Delisting',
};

export const CATALYST_VERDICT_TITLES: Record<string, string> = {
  catalyst: 'Catalyst',
  negative: 'Only dilution / delisting news',
  routine_only: 'Only routine company items -- no catalyst',
  noise_only: 'Only movers lists, law firms or opinion -- no catalyst',
  none_found: 'No news for this symbol since the prior close',
  not_checked: 'Catalyst not checked',
};

/** Where an item came from, as the desk says it. */
export const CATALYST_SOURCE_LABELS: Record<string, string> = {
  edgar: 'SEC',
  globenewswire: 'GlobeNewswire',
  prnewswire: 'PR Newswire',
  newsfile: 'Newsfile',
  fda: 'FDA',
  alpaca: 'Alpaca',
};

/** Sources that are the company's own release (a filing or a wire), not a rewrite of it. */
export const CATALYST_PRIMARY_SOURCES: readonly string[] = ['edgar', 'globenewswire', 'prnewswire', 'newsfile', 'fda'];

/** News column tooltips beyond the verdict titles. */
export const CATALYST_NEWS_UNREAD_TITLE = 'News not read yet for this symbol';
export const CATALYST_NEWS_UNPLACED_NOTE = 'A company headline no rule placed -- read it before trusting it';
export const CATALYST_NEWS_PENDING_TITLE = 'Halted for news -- the release is still to come';
export const CATALYST_NEWS_CHECKED_PREFIX = 'Checked';
export const CATALYST_NEWS_ALSO_NEGATIVE = 'Also: an offering / dilution item';

/** The Trader's News panel. */
export const CATALYST_PANEL_PATH = '/api/catalysts';
export const CATALYST_PANEL_POLL_MS = 60_000;
export const CATALYST_PANEL_UNREAD = 'Checking news since the prior close ...';
export const CATALYST_PANEL_HIDDEN_NOISE = 'movers lists / market wraps hidden';
export const CATALYST_PANEL_NO_COMPANY_ITEMS = 'No company items since the prior close';

/**
 * The catalyst classifier's verdict (ADR 024; backend `catalysts/live.py` WIRE_KEYS): what a
 * symbol's news since the prior session's close actually is -- not merely that an article exists.
 * Carried on scanner rows (`row.catalyst`), the setup board's pillars and the Trader's News panel.
 */
export type CatalystVerdictKind =
  | 'catalyst'
  | 'negative'
  | 'routine_only'
  | 'noise_only'
  | 'none_found'
  | 'not_checked';

export interface CatalystVerdict {
  verdict: CatalystVerdictKind;
  category: string | null;
  strength: 'strong' | 'weak' | null;
  /** The representative item's title. EDGAR titles read "<form: items> | <release headline>". */
  title: string | null;
  /** alpaca | edgar | globenewswire | prnewswire | newsfile | fda */
  source: string | null;
  /** Epoch seconds. */
  published_ts: number | null;
  url: string | null;
  /** A dilution / delisting item was also in the window. */
  negative_too: boolean;
  rules_version: string;
  /** Sources that looked across the whole window (alpaca, edgar, globenewswire, prnewswire, newsfile). */
  sources_answered?: string[];
  /** Items read in the window. */
  n_items?: number;
  /** A Nasdaq T1 / T12 halt inside the window with no resumption yet: the news is coming. */
  news_pending?: boolean;
  halt_code?: string | null;
}

/** One item the verdict read, as the News panel lists it (`GET /api/catalysts/{symbol}`). */
export interface CatalystItem {
  item_id: string | null;
  source: string | null;
  publisher: string | null;
  published_ts: number;
  title: string | null;
  url: string | null;
  kind: 'catalyst' | 'negative' | 'routine' | 'noise';
  category: string;
  strength: 'strong' | 'weak' | null;
  dilution: boolean;
}

export interface CatalystPanel {
  schema_version: number;
  symbol: string;
  generated_at: number;
  window_start: number;
  /** Null: no source looked yet -- unknown, never "no news". */
  verdict: CatalystVerdict | null;
  items: CatalystItem[];
  items_total: number;
}

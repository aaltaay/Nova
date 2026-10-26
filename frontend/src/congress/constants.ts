/**
 * The Congress page's paths, timings and words (ADR 066). Prices come only from IBKR's daily bars (the desk's own
 * `/api/ticker/{symbol}/bars`); every trade is a row of a member's own report.
 */
import type { Filter, Period } from './types';

export const CONGRESS_SCHEMA_VERSION = 1;
export const CONGRESS_BOARD_PATH = '/api/congress/board';
export const CONGRESS_MEMBERS_PATH = '/api/congress/members';
export const CONGRESS_MEMBER_PATH = '/api/congress/member';
export const CONGRESS_TRADES_PATH = '/api/congress/trades';
export const CONGRESS_PHOTO_PATH = '/api/congress/photo';
export const CONGRESS_CONSENT_PATH = '/api/congress/consent';
export const CONGRESS_BARS_PATH = (symbol: string) =>
  `/api/ticker/${encodeURIComponent(symbol)}/bars?timeframe=1Day&limit=300`;

export const CONGRESS_POLL_MS = 60_000;
/** While the reader is busy (the first read takes a while) or the agreement is pending. */
export const CONGRESS_BUSY_POLL_MS = 8_000;
export const CONGRESS_MOVES_REFRESH_MS = 10 * 60_000;
export const CONGRESS_FILLING_RETRY_MS = 5_000;

export const CONGRESS_PREFS_STORAGE_KEY = 'nova.congress.prefs.v1';
export const CONGRESS_PREFS_SCHEMA_VERSION = 1;

export const CONGRESS_TITLE = 'Congress';
export const CONGRESS_SUBTITLE =
  'Stock trades members of Congress reported. A trade shows up about four weeks after it happened.';
export const CONGRESS_OLD_API = 'This backend has no Congress page yet: update Nova to read the reports.';
export const CONGRESS_OFF = 'The Congress page is off on this desk (NOVA_CONGRESS=0).';

export const PERIODS: readonly Period[] = ['ytd', '90d', '30d'];
export const periodLabel = (p: Period, year: number): string => (p === 'ytd' ? String(year) : p.toUpperCase());

export const FILTERS: readonly { id: Filter | 'following'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'house', label: 'House' },
  { id: 'senate', label: 'Senate' },
  { id: 'buys', label: 'Bought' },
  { id: 'sells', label: 'Sold' },
  { id: 'options', label: 'Options' },
  { id: 'late', label: 'Reported late' },
  { id: 'following', label: 'Following' },
];

export const PARTY_COLOR: Record<string, string> = { D: '#0a84ff', R: '#ff453a', I: '#a78bfa' };
export const PARTY_NAME: Record<string, string> = { D: 'Democrat', R: 'Republican', I: 'Independent' };
export const OWNER_WORD: Record<string, string> = { self: 'Self', spouse: 'Spouse', joint: 'Joint', child: 'Child' };

export const LATE_DAYS = 45;
export const HOW_LATE_HELP =
  'Days from each trade to the report that made it public, for every trade reported this year. The law allows ' +
  '30 days from learning of a trade and never more than 45 days after it; a late report costs $200.';
export const SEATS_HELP =
  'Every seat, seated by party -- Democrats from the left. The House has no assigned seats, so this is not the ' +
  'floor chart. A photo or a lit seat: the member reported trades in the period.';
export const PAPER_WORDS = 'Paper filing, scanned · not read by Nova';
export const CONSENT_TITLE = 'Before Nova reads the reports';
export const CONSENT_LEAD =
  'Nova reads the House Clerk’s and the Senate’s public reports on this computer, for you, and sends ' +
  'nothing anywhere. Both sites ask anyone who reads the reports to agree to this rule first:';
export const CONSENT_BUTTON = 'I understand';
export const SAMPLE_NOTE = 'Nova Marketing Sample Data: invented members and trades, not real reports.';

/**
 * What the bar's ticker search was asked. Pure.
 *
 * - `/pattern/` (trailing slash optional) is a case-insensitive regex over
 *   symbols -- `/^A..X$/`, `/^[A-Z]{5}$/`, `/Q$/`.
 * - A `*` or `?` makes a wildcard over the whole symbol -- `A*X`, `??Q`.
 * - Anything else is text: a symbol prefix or a company name.
 *
 * Patterns only ever run over symbols (a few characters each), so a heavy
 * regex cannot stall the desk; they are also capped in length.
 */
import { GLOBAL_BAR_SEARCH_PATTERN_MAX_CHARS } from '../constantGroups/global_bar';

export type TickerQuery =
  | { kind: 'empty' }
  | { kind: 'text'; text: string }
  | { kind: 'pattern'; flavor: 'regex' | 'wildcard'; regex: RegExp }
  | { kind: 'invalid'; message: string };

const WILDCARD = /[*?]/;
/** Characters a wildcard may hold besides * and ?: what symbols are made of. */
const WILDCARD_OK = /^[A-Z0-9.\-/ *?]+$/;

export function isRegexInput(raw: string): boolean {
  return raw.trimStart().startsWith('/');
}

export function parseTickerQuery(raw: string): TickerQuery {
  const trimmed = raw.trim();
  if (!trimmed) return { kind: 'empty' };
  if (trimmed.startsWith('/')) {
    let body = trimmed.slice(1);
    if (body.endsWith('/') && !body.endsWith('\\/')) body = body.slice(0, -1);
    if (!body) return { kind: 'invalid', message: 'Regex: type a pattern, e.g. /^A..X$/' };
    if (body.length > GLOBAL_BAR_SEARCH_PATTERN_MAX_CHARS) {
      return { kind: 'invalid', message: `Regex: ${GLOBAL_BAR_SEARCH_PATTERN_MAX_CHARS} characters at most` };
    }
    try {
      return { kind: 'pattern', flavor: 'regex', regex: new RegExp(body, 'i') };
    } catch (err) {
      const detail = err instanceof Error ? err.message.replace(/^Invalid regular expression: /, '') : '';
      return { kind: 'invalid', message: `Regex: ${detail || 'not a valid pattern'}` };
    }
  }
  const text = trimmed.toUpperCase().replace(/\s+/g, ' ');
  if (WILDCARD.test(text)) {
    if (!WILDCARD_OK.test(text) || text.length > GLOBAL_BAR_SEARCH_PATTERN_MAX_CHARS) {
      return { kind: 'invalid', message: 'Wildcard: letters, digits, * and ? only' };
    }
    const source = text
      .replace(/ /g, '')
      .replace(/[.\-/]/g, (c) => `\\${c}`)
      .replace(/\*/g, '.*')
      .replace(/\?/g, '.');
    return { kind: 'pattern', flavor: 'wildcard', regex: new RegExp(`^${source}$`, 'i') };
  }
  return { kind: 'text', text };
}

/** Could this text be a ticker as typed (so it earns the "open exactly this" row)? */
export function looksLikeSymbol(text: string): boolean {
  return /^[A-Z0-9][A-Z0-9.\-/]{0,9}$/.test(text);
}

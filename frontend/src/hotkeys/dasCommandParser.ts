/**
 * Case-preserving DAS command tokenizer.
 * Does not execute commands. Never rewrites original casing.
 */

import type { DasCommandToken, DasCommandTokenKind } from './types';

const CANCEL_RE = /^CXL(\s|$)/i;
const URL_RE = /^(https?:\/\/|www\.)/i;
const FOCUS_RE = /^(FOCUS|FocusWindow|SwitchTWnd|GetWindowObj)/i;
const TRIGGER_RE = /^(TriggerOrder|WithTrigger)\s*=/i;

function classifyAssignment(name: string, value: string | undefined): DasCommandTokenKind {
  const n = name.toUpperCase();
  if (n === 'TRIGGERORDER' || n === 'WITHTRIGGER') return 'trigger';
  if (n === 'BUY' || n === 'SELL' || n === 'SEND' || n === 'LOAD') return 'action';
  if (value !== undefined) return 'assignment';
  return 'unknown';
}

/**
 * Split a command string on top-level semicolons.
 * Nested TriggerOrder=RT:STOP ... segments stay intact (no semicolon nesting).
 */
export function splitCommandSegments(command: string): string[] {
  if (!command.trim()) return [];
  return command
    .split(';')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

/** Parse one segment into a token without mutating casing. */
export function parseSegment(segment: string): DasCommandToken {
  const raw = segment.trim();
  if (!raw) {
    return { raw, kind: 'unknown', name: '' };
  }

  if (URL_RE.test(raw) || raw.toLowerCase().startsWith('http://') || raw.includes('://')) {
    // Plain URL or finance.yahoo.com/... style
    if (raw.includes('://') || raw.toLowerCase().startsWith('www.') || raw.includes('%SYMB%')) {
      // Prefer URL for web-looking commands without '='
      if (!raw.includes('=') || raw.startsWith('http')) {
        return { raw, kind: 'url', name: 'URL', value: raw };
      }
    }
  }

  if (CANCEL_RE.test(raw)) {
    return { raw, kind: 'cancel', name: raw };
  }

  if (FOCUS_RE.test(raw) && !raw.includes('=')) {
    return { raw, kind: 'focus', name: raw };
  }

  if (TRIGGER_RE.test(raw)) {
    const eq = raw.indexOf('=');
    return {
      raw,
      kind: 'trigger',
      name: raw.slice(0, eq),
      value: raw.slice(eq + 1),
    };
  }

  // Bare BUY / SELL / SEND=Reverse / NewOrder Market
  const eq = raw.indexOf('=');
  if (eq < 0) {
    const upper = raw.toUpperCase();
    if (upper === 'BUY' || upper === 'SELL' || upper.startsWith('NEWORDER')) {
      return { raw, kind: 'action', name: raw };
    }
    if (URL_RE.test(raw) || raw.includes('%SYMB%') || /\.(com|net|org)\//i.test(raw)) {
      return { raw, kind: 'url', name: 'URL', value: raw };
    }
    return { raw, kind: 'unknown', name: raw };
  }

  const name = raw.slice(0, eq);
  const value = raw.slice(eq + 1);
  const kind = classifyAssignment(name, value);
  return { raw, kind, name, value };
}

/** Tokenize a full DAS command string. Preserves original segment text. */
export function tokenizeDasCommand(command: string): DasCommandToken[] {
  return splitCommandSegments(command).map(parseSegment);
}

/** Join tokens back — only for diagnostics; prefer original command for export. */
export function joinDasTokens(tokens: DasCommandToken[]): string {
  return tokens.map((t) => t.raw).join(';');
}

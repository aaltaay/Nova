/**
 * A setup row's grade (ADR 022), counted: "C 1/5" -- the letter and how many of the Five Pillars
 * pass -- with each pillar and its value on hover, and when it was read: when the setup armed, or,
 * while the pattern forms, when its leg made its high (operator report, 2026-09-29: "how do we know
 * the grades as a human?"). Pure: a row in, words out.
 */
import { SETUP_GRADE_TIP, SETUP_PILLAR_WORDS } from '../constantGroups/setups';
import { SHORT_GRADE_TIP, SHORT_PILLAR_WORDS } from '../constantGroups/short_setups';
import { catalystTitle, fmtPx } from './setupsFormat';
import { isShortRow } from './shortWords';
import type { Words } from './setupWords';
import type { SetupPillars, SetupRow } from './types';

export interface PillarCount {
  passed: number;
  known: number;
  total: number;
}

/** How many pillars pass and how many are known; null without checks. */
export function pillarCount(checks: Record<string, boolean | null> | null | undefined): PillarCount | null {
  const values = Object.values(checks ?? {});
  if (!values.length) return null;
  return {
    passed: values.filter(v => v === true).length,
    known: values.filter(v => v !== null && v !== undefined).length,
    total: values.length,
  };
}

/** "C 1/5"; the letter alone when no checks came with it; null with no grade. */
export function gradeLabel(grade: string | null | undefined, count: PillarCount | null): string | null {
  if (!grade) return null;
  return count ? `${grade} ${count.passed}/${count.total}` : grade;
}

const PILLAR_ORDER: [string, string][] = [
  ['price', 'price'], ['change', 'change_pct'], ['rvol', 'rvol'], ['float', 'float'], ['news', 'news'],
];
/** A short's pillars (ADR 049 section 10): each check with the value it read. */
const SHORT_ORDER: [string, string][] = [
  ['run', 'run'], ['fade', 'fade'], ['vwap', 'vwap'], ['bad_news', 'bad_news'], ['borrow', 'borrow'],
];

function signedWhole(pct: number): string {
  return `${pct > 0 ? '+' : pct < 0 ? '−' : ''}${Math.abs(pct).toFixed(0)}%`;
}

function pillarValue(key: string, p: SetupPillars): string {
  switch (key) {
    case 'price': return p.price != null ? fmtPx(p.price) : 'unknown';
    case 'change_pct': return p.change_pct != null ? signedWhole(p.change_pct) : 'unknown';
    case 'rvol': return p.rvol != null ? `${p.rvol.toFixed(1)}x` : 'unknown';
    case 'float': return p.float != null ? `${(p.float / 1e6).toFixed(1)}M` : 'unknown';
    case 'news': return p.headline ? p.headline : p.news == null ? 'not read' : p.news ? 'a catalyst' : 'none';
    default: return shortPillarValue(key, p);
  }
}

function shortPillarValue(key: string, p: SetupPillars): string {
  const unknown = 'unknown';
  switch (key) {
    case 'run': return p.run_pct != null ? `high of day ${signedWhole(p.run_pct)} over the prior close` : unknown;
    case 'fade': return p.fade_pct != null ? `${p.fade_pct.toFixed(1)}% under the high of day` : unknown;
    case 'vwap': return p.price != null && p.vwap != null ? `${fmtPx(p.price)} vs VWAP ${fmtPx(p.vwap)}` : unknown;
    case 'bad_news': {
      const b = p.bad_news;
      if (!b) return 'not read';
      if (b.text) return b.text;
      if (b.dilution === true || b.negative === true) return b.dilution ? 'dilution on file' : 'negative news';
      return b.dilution === false && b.negative === false ? 'none on file' : 'not read';
    }
    case 'borrow': {
      const b = p.borrow;
      if (!b || b.shares == null) return 'not read';
      const order = b.order_shares != null ? ` for a ${b.order_shares.toLocaleString('en-US')}-share order` : '';
      return `${b.shares.toLocaleString('en-US')} shortable${order}`;
    }
    default: return '';
  }
}

const WHEN: Record<string, string> = {
  armed: 'Read when the setup armed.',
  forming: 'Read when this leg made its high; graded again when the setup arms.',
};

/** The grade chip: "C 1/5", each pillar with its value, when it was read, and what News rested on. */
export function gradeWords(row: SetupRow): Words {
  const p = row.pillars;
  if (!row.grade || !p) {
    return { text: '·', title: 'Grade', tip: `${SETUP_GRADE_TIP}\nGraded when its leg makes a high, and again when it arms.` };
  }
  const short = isShortRow(row);
  const checks = p.checks ?? {};
  const count = pillarCount(checks);
  const head = count
    ? `Grade ${row.grade}: ${count.passed} of ${count.total} pillars pass`
      + `${count.known < count.total ? ` (${count.total - count.known} not known)` : ''}.`
    : `Grade ${row.grade}.`;
  const lines = [head, short ? SHORT_GRADE_TIP : SETUP_GRADE_TIP];
  const when = WHEN[row.graded ?? ''];
  if (when) lines.push(when);
  for (const [checkKey, valueKey] of short ? SHORT_ORDER : PILLAR_ORDER) {
    const ok = checks[checkKey];
    const mark = ok === true ? '✓' : ok === false ? '✗' : '?';
    const name = (short ? SHORT_PILLAR_WORDS[valueKey] : SETUP_PILLAR_WORDS[valueKey]) ?? valueKey;
    lines.push(`${mark} ${name}: ${pillarValue(valueKey, p)}`);
  }
  const note = (p as { float_note?: string | null }).float_note;
  if (note) lines.push(`Float: ${note.replace(/ -- /g, ' — ')}`);
  if (!short) lines.push(catalystTitle(p));
  const text = gradeLabel(row.grade, count) ?? row.grade;
  return { text, title: `Grade ${text}`, tip: lines.join('\n') };
}

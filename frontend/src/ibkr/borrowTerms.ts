/**
 * The borrow in a trader's words (ETB / HTB / LOCATE / NSS), as the backend's `borrow` terms say it
 * (backend/ibkr/borrow_terms.py): the Level 2 chip's class and its hover, both sources with their time.
 */
import type { BorrowTerms } from '../types/ticker';

const ET_CLOCK = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
});

function clock(ts: number): string {
  return ET_CLOCK.format(new Date(ts * 1000));
}

function shares(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

function fee(f: number): string {
  return f >= 10 ? `${f.toFixed(0)}%` : `${Number(f.toFixed(1))}%`;
}

export function borrowChipClass(borrow: BorrowTerms): string {
  if (borrow.tone === 'ok') return 'sv-shortability-chip--ok';
  if (borrow.tone === 'warn') return 'sv-shortability-chip--thin';
  if (borrow.tone === 'bad') return 'sv-shortability-chip--nss';
  return 'sv-shortability-chip--unknown';
}

/** The chip's hover: the verdict, then what each IBKR source said and when. */
export function borrowTip(borrow: BorrowTerms, ageSec?: number | null): string {
  const lines = [borrow.text];
  const age = ageSec != null && Number.isFinite(ageSec) ? `, ${Math.round(ageSec)} s ago` : '';
  if (borrow.shares != null) lines.push(`Live (IBKR${age}): ${shares(borrow.shares)} shares to lend`);
  else if (borrow.level != null) lines.push(`Live (IBKR${age}): no share count, shortable level ${borrow.level}`);
  else lines.push(`Live (IBKR${age}): no share count`);
  const list = borrow.list;
  if (list) {
    const asOf = list.as_of != null ? ` (as of ${clock(list.as_of)} ET)` : '';
    if (!list.listed) {
      const since = list.changed_at != null && list.was?.listed ? ` since ${clock(list.changed_at)} ET` : '';
      const was = list.was?.listed
        ? ` -- was ${[list.was.available != null ? shares(list.was.available) : null,
          list.was.fee_rate != null ? `@ ${fee(list.was.fee_rate)}/yr` : null].filter(Boolean).join(' ')}`
        : '';
      lines.push(`IBKR's short-stock list${asOf}: not listed${since}${was}`);
    } else {
      const avail = list.available != null ? `${shares(list.available)}${list.capped ? '+' : ''} shares` : 'listed';
      const rate = list.fee_rate != null ? ` @ ${fee(list.fee_rate)}/yr` : '';
      lines.push(`IBKR's short-stock list${asOf}: ${avail}${rate}`);
    }
  } else {
    lines.push("IBKR's short-stock list: not read");
  }
  if (borrow.list_note) lines.push(borrow.list_note);
  lines.push('ETB: easy to borrow · HTB: hard to borrow (a fee over 10%/yr, or under 10K shares) · LOCATE: a locate is needed · NSS: not shortable');
  return lines.join('\n');
}

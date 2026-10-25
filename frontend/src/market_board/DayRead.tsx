/**
 * The day read (ADR 053): Bullish / Mixed / Bearish with the six checks that make it, and the day's events. Above it,
 * the small-cap temperature of the day, the week and the month (ADR 053 amendment 2026-10-25) -- the climate card's
 * labels, a separate question that never moves the verdict.
 */
import { useState } from 'react';
import { DAY_READ_RULE, TEMP_WORD, VERDICT_WORD } from './constants';
import { etTime, etWhen } from './format';
import type { Check, DayRead, Events } from './types';

const ICON: Record<Check['state'], string> = { green: '✓', amber: '!', red: '✗', waiting: '–', unknown: '?' };
const SPANS = ['day', 'week', 'month'] as const;

function SmallCapTemperature({ t }: { t: NonNullable<DayRead['temperature']> }) {
  return (
    <p className="mk-read__temp" data-testid="market-day-read-temperature"
      title="The Small-cap climate card's temperature. Not one of the checks: it never moves the verdict.">
      <span className="mk-muted">Small caps</span>
      {SPANS.map((k) => {
        const label = t[k];
        return (
          <span key={k} className={`mk-temp is-${label ?? 'none'}`}>
            {label ? TEMP_WORD[label].toLowerCase() : '--'} {k}
          </span>
        );
      })}
    </p>
  );
}

function checkTitle(c: Check): string | undefined {
  if (c.state === 'waiting' && c.starts_at) return `Starts at ${etTime(c.starts_at)} ET`;
  return c.why ?? undefined;
}

export function DayReadCard({ read, events, now }: { read: DayRead; events: Events; now: number }) {
  const [rule, setRule] = useState(false);
  const word = read.verdict ? VERDICT_WORD[read.verdict] : '--';
  const waiting = read.checks.filter((c) => c.state === 'waiting').length;
  const score = read.verdict
    ? `${read.green} of ${read.known} checks green${waiting ? ` · ${waiting} start at 09:30` : ''}`
    : `not enough data yet (${read.known} of ${read.total} checks)`;
  const bond = events.bond_market;
  return (
    <section className="mk-card mk-read" data-testid="market-day-read">
      <header className="mk-card__head">
        <h3>Day read</h3>
        <span className="mk-hint">is today bullish or bearish?</span>
        <button type="button" className="mk-link mk-push" aria-expanded={rule} onClick={() => setRule((v) => !v)}>
          how it&apos;s read &#9432;
        </button>
      </header>
      {rule ? <p className="mk-read__rule" role="note">{DAY_READ_RULE}</p> : null}
      {read.temperature ? <SmallCapTemperature t={read.temperature} /> : null}
      <div className="mk-read__verdict">
        <span className={`mk-read__word is-${read.verdict ?? 'none'}`}>{word}</span>
        <span className="mk-hint">{score}</span>
      </div>
      <div className="mk-read__meter" aria-hidden="true">
        {(['bearish', 'mixed', 'bullish'] as const).map((v) => (
          <i key={v} className={`is-${v}${read.verdict === v ? ' is-on' : ''}`} />
        ))}
        <span>Bearish</span><span>Mixed</span><span>Bullish</span>
      </div>
      <ul className="mk-read__checks">
        {read.checks.map((c) => (
          <li key={c.id} className={`is-${c.state}`} title={checkTitle(c)}>
            <span className="mk-read__icon">{ICON[c.state]}</span>
            <span className="mk-read__label">{c.label}</span>
            <span className="mk-read__value">{c.text}</span>
          </li>
        ))}
      </ul>
      <p className="mk-read__events">
        {bond.closed ? <span>Bond market closed today ({bond.why}) · </span> : null}
        {bond.early_close_at ? <span>Bonds close at {etTime(bond.early_close_at)} ({bond.why}) · </span> : null}
        {events.items.length === 0 ? <span className="mk-muted">No scheduled reports in the next days.</span> : null}
        {events.items.map((e, i) => (
          <span key={`${e.at}-${e.title}`} title={`${e.detail ?? e.title} · source: ${e.source.toUpperCase()}`}>
            {i ? ' · ' : ''}
            <b>{etWhen(e.at, now)}</b> {e.title}
          </span>
        ))}
      </p>
    </section>
  );
}

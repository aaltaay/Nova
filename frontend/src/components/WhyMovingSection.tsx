/**
 * "Why it's moving" (ADR 028): the rules read of what drove the move, at the top of the Trader's News panel.
 * The likely cause shows in the header, open or folded; the body lists every check -- yes, no or unknown --
 * with the value that decided it, and each row's source and age on hover. Nothing here is a control
 * except the fold.
 */
import { useState } from 'react';
import {
  WHY_MOVING_DEFAULT_EXPANDED,
  WHY_MOVING_POSSIBLE_TITLE,
  WHY_MOVING_READING,
  WHY_MOVING_RULES_NOTE,
  WHY_MOVING_STATE_MARKS,
  WHY_MOVING_STATE_TITLES,
  WHY_MOVING_TITLE,
  WHY_MOVING_TONES,
} from '../constants';
import type { WhyCheck, WhyMovingRead } from '../types/whyMoving';
import { agoLabel } from '../utils/catalystVerdict';
import './whyMoving.css';

interface Props {
  read: WhyMovingRead | null;
  loading?: boolean;
  error?: string | null;
}

function rowTitle(c: WhyCheck, nowMs: number): string {
  const age = c.as_of != null ? `as of ${agoLabel(c.as_of, nowMs)}` : '';
  return [WHY_MOVING_STATE_TITLES[c.state], c.source, age].filter(Boolean).join(' · ');
}

function CheckRow({ c, nowMs }: { c: WhyCheck; nowMs: number }) {
  return (
    <li className={`wm-check wm-check--${c.state}`} data-check={c.id} data-state={c.state} title={rowTitle(c, nowMs)}>
      <span className="wm-check-mark" aria-label={WHY_MOVING_STATE_TITLES[c.state]}>
        {WHY_MOVING_STATE_MARKS[c.state] ?? '?'}
      </span>
      <span className="wm-check-label">{c.label}</span>
      <span className="wm-check-value">{c.value ?? '—'}</span>
      {c.detail && <span className="wm-check-detail">{c.detail}</span>}
    </li>
  );
}

export function WhyMovingSection({ read, loading = false, error = null }: Props) {
  const [expanded, setExpanded] = useState(WHY_MOVING_DEFAULT_EXPANDED);
  const nowMs = Date.now();
  const likely = read?.likely ?? null;
  const tone = likely ? WHY_MOVING_TONES[likely.kind] ?? 'muted' : 'muted';
  // "--" as two non-breaking hyphens, so a wrapped header never splits it across lines.
  const headline = (likely?.label ?? (!read && error ? error : WHY_MOVING_READING)).replace(/--/g, '‑‑');
  const possible = likely?.confidence === 'possible';

  return (
    <div
      className={`cq-news-section wm-section wm-tone--${tone}${expanded ? ' cq-news-section--expanded' : ' cq-news-section--collapsed'}`}
      data-why-kind={likely?.kind ?? ''}
      data-why-expanded={expanded ? 'true' : 'false'}
    >
      <button
        type="button"
        className="cq-news-header cq-news-toggle"
        onClick={() => setExpanded((x) => !x)}
        aria-expanded={expanded}
        aria-controls="wm-body"
        title={expanded ? 'Hide the checks' : 'Show the checks behind this read'}
      >
        <span className="cq-news-toggle-left">
          <span className="cq-news-chevron" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
          <span className="cq-news-title">{WHY_MOVING_TITLE}</span>
          <span className="cq-news-preview wm-headline" title={likely?.detail ?? headline}>
            {loading && !read ? WHY_MOVING_READING : headline}
          </span>
        </span>
        {possible && <span className="wm-possible" title={WHY_MOVING_POSSIBLE_TITLE}>possible</span>}
      </button>

      {expanded && (
        <div className="cq-news-body wm-body" id="wm-body">
          {error && <div className="cn-error" role="status">{error}</div>}
          {likely?.detail && <p className="wm-detail">{likely.detail}</p>}
          {read ? (
            <ul className="wm-checks">
              {read.checks.map((c) => <CheckRow key={c.id} c={c} nowMs={nowMs} />)}
            </ul>
          ) : (
            <div className="wm-reading">{WHY_MOVING_READING}</div>
          )}
          {read && <div className="wm-note">{WHY_MOVING_RULES_NOTE}</div>}
        </div>
      )}
    </div>
  );
}

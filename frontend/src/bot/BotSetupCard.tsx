/**
 * One setup of the operator's playbook (ADR 027): a radio to play it, its own
 * level switch, and what the research said. Only a setup with a live scanner
 * can be played; the others show why not instead of looking like buttons that
 * do nothing.
 */
import type { ReactNode } from 'react';
import {
  BOT_CHOSEN_BADGE,
  BOT_LEVEL_LABELS,
  BOT_NO_SCANNER_TITLE,
  BOT_SETUP_BLURBS,
  BOT_SETUP_LABELS,
  BOT_SETUP_NEXT,
  BOT_SETUP_RESEARCH,
} from '../constantGroups/bot';
import { BOTS_RESEARCH_BADGES, BOTS_SETUP_LEVEL_TITLE, BOTS_SETUP_PICK_TITLE } from '../constantGroups/bots_page';

const LEVELS = [0, 1, 2] as const;

interface Props {
  id: string;
  chosen: boolean;
  /** The setup has a live scanner, so it may be played. */
  playable: boolean;
  /** The session level (only the chosen setup carries it). */
  level: number;
  busy: boolean;
  onChoose: (id: string) => void;
  onLevel: (level: number) => void;
  children?: ReactNode;
}

/** "Bars alone: failed" as a badge, then the rest of the research line. */
function Research({ id }: { id: string }) {
  const research = BOT_SETUP_RESEARCH[id];
  if (!research) return null;
  return (
    <p className={`bots-strat__research bots-strat__research--${research.verdict}`}>
      <span className="bots-rbadge">{BOTS_RESEARCH_BADGES[research.verdict] ?? research.verdict}</span> {research.detail}
    </p>
  );
}

export function BotSetupCard({ id, chosen, playable, level, busy, onChoose, onLevel, children }: Props) {
  const shown = chosen ? (level > 2 ? 2 : level) : 0;
  const levelLocked = !chosen || !playable;
  const lockTitle = playable ? BOTS_SETUP_PICK_TITLE : BOT_NO_SCANNER_TITLE;
  return (
    <article className={`bots-strat${chosen ? ' bots-strat--chosen' : ''}${playable ? '' : ' bots-strat--noscan'}`}
      data-testid={`bots-setup-${id}`}>
      <div className="bots-strat__head">
        <label className="bots-strat__pick" title={chosen ? undefined : lockTitle}>
          <input
            type="radio"
            name="bots-setup"
            data-testid={`bots-setup-radio-${id}`}
            aria-label={`${BOTS_SETUP_PICK_TITLE}: ${BOT_SETUP_LABELS[id] ?? id}`}
            checked={chosen}
            disabled={busy || !playable}
            onChange={() => { if (!chosen && playable) onChoose(id); }}
          />
          <b>{BOT_SETUP_LABELS[id] ?? id}</b>
        </label>
        {chosen ? <span className="bots-badge">★ {BOT_CHOSEN_BADGE}</span> : null}
        <span className="bots-levels" role="radiogroup" aria-label={`${BOT_SETUP_LABELS[id] ?? id} level`}
          title={levelLocked ? BOT_NO_SCANNER_TITLE : BOTS_SETUP_LEVEL_TITLE}>
          {LEVELS.map(n => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={shown === n}
              className={`bots-levels__opt${shown === n ? ' is-on' : ''}`}
              data-testid={`bots-setup-level-${id}-${n}`}
              disabled={busy || levelLocked}
              onClick={() => { if (shown !== n) onLevel(n); }}
            >
              {BOT_LEVEL_LABELS[n]}
            </button>
          ))}
        </span>
      </div>
      {children ?? (
        <>
          <p className="bots-strat__blurb">{BOT_SETUP_BLURBS[id]}</p>
          <Research id={id} />
          <p className="bots-strat__next">{playable ? 'Scanner live' : BOT_SETUP_NEXT[id] ?? 'No scanner yet'}</p>
        </>
      )}
    </article>
  );
}

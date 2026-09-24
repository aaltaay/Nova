/**
 * One setup of the operator's playbook (ADR 027, ADR 029): a radio to play it,
 * its own level switch, the template in play with its rules in words -- built
 * from the numbers the scanner runs, never hand-written -- and a door to every
 * parameter. Only a setup with a live scanner can be played; every locked
 * control says why on hover.
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
import {
  BOTS_BUSY_WHY,
  BOTS_RESEARCH_BADGES,
  BOTS_SETUP_LEVEL_TITLE,
  BOTS_SETUP_NOT_CHOSEN_WHY,
  BOTS_SETUP_PICK_TITLE,
  BOTS_TEMPLATE_LABEL,
  BOTS_TEMPLATE_LOADING_WHY,
  BOTS_TEMPLATE_NO_PARAMS_WHY,
  BOTS_TEMPLATE_PARAMS,
  BOTS_TEMPLATE_PICK_TITLE,
  BOTS_TEMPLATE_SAVING_WHY,
  BOTS_TEMPLATE_UNREAD_WHY,
} from '../constantGroups/bots_page';
import { readoutText, ruleLines } from './templateFormat';
import type { SetupTemplates } from './templateTypes';

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
  /** This setup's templates (ADR 029); null while they load or when they did not. */
  templates: SetupTemplates | null;
  templatesError?: string | null;
  /** A template write (put in play) is in flight. */
  templateBusy?: boolean;
  onPlayTemplate?: (setupId: string, templateId: string) => void;
  onOpenParams?: (setupId: string) => void;
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

function templateWhy(t: SetupTemplates | null, error: string | null | undefined, busy: boolean): string | null {
  if (!t) return error ? BOTS_TEMPLATE_UNREAD_WHY(error) : BOTS_TEMPLATE_LOADING_WHY;
  if (t.catalogue.groups.length === 0) return BOTS_TEMPLATE_NO_PARAMS_WHY;
  return busy ? BOTS_TEMPLATE_SAVING_WHY : null;
}

export function BotSetupCard({
  id, chosen, playable, level, busy, onChoose, onLevel, templates, templatesError = null, templateBusy = false,
  onPlayTemplate, onOpenParams, children,
}: Props) {
  const shown = chosen ? (level > 2 ? 2 : level) : 0;
  const pickWhy = !playable ? BOT_NO_SCANNER_TITLE : busy ? BOTS_BUSY_WHY : null;
  const levelWhy = !playable ? BOT_NO_SCANNER_TITLE : !chosen ? BOTS_SETUP_NOT_CHOSEN_WHY : busy ? BOTS_BUSY_WHY : null;
  const label = BOT_SETUP_LABELS[id] ?? id;
  const inPlay = templates?.templates.find(t => t.id === templates.in_play) ?? null;
  const lines = inPlay ? ruleLines(id, inPlay.values) : [];
  const nParams = templates?.catalogue.groups.reduce((n, g) => n + g.params.length, 0) ?? 0;
  const tplWhy = templateWhy(templates, templatesError, templateBusy);
  const paramsWhy = templates ? (nParams === 0 ? BOTS_TEMPLATE_NO_PARAMS_WHY : null) : tplWhy;
  const progress = inPlay ? readoutText(inPlay) : null;
  return (
    <article className={`bots-strat${chosen ? ' bots-strat--chosen' : ''}${playable ? '' : ' bots-strat--noscan'}`}
      data-testid={`bots-setup-${id}`}>
      <div className="bots-strat__head">
        <label className="bots-strat__pick" title={chosen || pickWhy ? undefined : BOTS_SETUP_PICK_TITLE}>
          <input
            type="radio"
            name="bots-setup"
            data-testid={`bots-setup-radio-${id}`}
            aria-label={`${BOTS_SETUP_PICK_TITLE}: ${label}`}
            checked={chosen}
            disabled={pickWhy != null}
            data-why={pickWhy ?? undefined}
            onChange={() => { if (!chosen && playable) onChoose(id); }}
          />
          <b>{label}</b>
        </label>
        {chosen ? <span className="bots-badge">★ {BOT_CHOSEN_BADGE}</span> : null}
        <span className="bots-levels" role="radiogroup" aria-label={`${label} level`}
          title={levelWhy ? undefined : BOTS_SETUP_LEVEL_TITLE}>
          {LEVELS.map(n => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={shown === n}
              className={`bots-levels__opt${shown === n ? ' is-on' : ''}`}
              data-testid={`bots-setup-level-${id}-${n}`}
              disabled={levelWhy != null}
              data-why={levelWhy ?? undefined}
              onClick={() => { if (shown !== n) onLevel(n); }}
            >
              {BOT_LEVEL_LABELS[n]}
            </button>
          ))}
        </span>
      </div>

      <div className="bots-strat__tpl">
        <label className="bots-strat__tplpick" title={tplWhy ? undefined : BOTS_TEMPLATE_PICK_TITLE}>
          <span>{BOTS_TEMPLATE_LABEL}</span>
          <select data-testid={`bots-setup-template-${id}`} value={templates?.in_play ?? ''}
            disabled={tplWhy != null} data-why={tplWhy ?? undefined}
            onChange={e => onPlayTemplate?.(id, e.target.value)}>
            {(templates?.templates ?? []).map(t => (
              <option key={t.id} value={t.id} disabled={Boolean(t.error)}>
                {t.name}{t.error ? ' (does not validate -- fix it first)' : ''}
              </option>
            ))}
            {!templates ? <option value="">{templatesError ? 'did not load' : 'loading…'}</option> : null}
          </select>
        </label>
        {progress && templates?.scanner ? <span className="bots-strat__tplstate" data-testid={`bots-setup-readout-${id}`}>{progress}</span> : null}
        <button type="button" className="bots-linkbtn" data-testid={`bots-setup-params-${id}`}
          disabled={paramsWhy != null} data-why={paramsWhy ?? undefined} onClick={() => onOpenParams?.(id)}>
          {BOTS_TEMPLATE_PARAMS(nParams)}
        </button>
      </div>

      {lines.length ? (
        <dl className="bots-rules" data-testid={`bots-setup-rules-${id}`}>
          {lines.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      ) : null}
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

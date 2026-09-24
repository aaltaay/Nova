/**
 * The operator's playbook on the Bots page (approved mockup v4, ADR 027, ADR
 * 029): the setup that plays -- first pullback, with the rules of its template
 * in play, the tape gate in that template's numbers and the read-out that
 * unlocks Strategy -- and the rest of the material's setups with their own
 * parameters and what the research said, each waiting on a scanner of its own.
 * Choosing a setup, its level and its template are real controls; every
 * parameter opens in the template editor. Nothing here places an order.
 */
import { useState, type ReactNode } from 'react';
import {
  BOT_SETUP_FIRST_PULLBACK,
  BOT_SETUP_IDS,
  TAPE_VERDICT_TITLES,
} from '../constants';
import {
  BOTS_ADD_SETUP_CLOSE,
  BOTS_ADD_SETUP_COPY,
  BOTS_ADD_SETUP_HINT,
  BOTS_ADD_SETUP_LABEL,
  BOTS_ADD_SETUP_MESSAGE,
  BOTS_CATALOGUE_PATH,
  BOTS_STRATEGIES_SOURCE,
  BOTS_STRATEGIES_SUB,
  BOTS_STRATEGIES_TITLE,
} from '../constantGroups/bots_page';
import { confirmApp } from '../ux/appDialogApi';
import { BotReadout } from './BotReadout';
import { BotSetupCard } from './BotSetupCard';
import { BotTemplateEditor } from './BotTemplateEditor';
import { tapeLines } from './templateFormat';
import { playTemplate } from './templatesApi';
import type { BotSession } from './types';
import { useSetupTemplates } from './useSetupTemplates';
import './botTemplates.css';

interface Props {
  session: BotSession;
  busy: boolean;
  onChooseSetup: (id: string) => void;
  onLevel: (level: number) => void;
}

/** "+ Add a setup": what adding one takes, and the catalogue's path on this PC. */
async function explainAddSetup(): Promise<void> {
  const copy = await confirmApp({
    title: BOTS_ADD_SETUP_LABEL,
    message: BOTS_ADD_SETUP_MESSAGE,
    confirmLabel: BOTS_ADD_SETUP_COPY,
    cancelLabel: BOTS_ADD_SETUP_CLOSE,
  });
  if (!copy) return;
  try {
    await navigator.clipboard.writeText(BOTS_CATALOGUE_PATH);
  } catch (err) {
    console.warn('[Nova] could not copy the catalogue path', err);
  }
}

export function BotStrategiesCard({ session, busy, onChooseSetup, onLevel }: Props) {
  const chosen = session.setup || BOT_SETUP_FIRST_PULLBACK;
  const scanner = new Map((session.setups ?? []).map(s => [s.id, s.scanner]));
  const others = BOT_SETUP_IDS.filter(id => id !== chosen);
  const tpl = useSetupTemplates();
  const [editing, setEditing] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [playError, setPlayError] = useState<string | null>(null);

  async function play(setupId: string, templateId: string) {
    setPlaying(true);
    setPlayError(null);
    try {
      tpl.apply(await playTemplate(setupId, templateId));
    } catch (err) {
      setPlayError(err instanceof Error ? err.message : String(err));
    } finally {
      setPlaying(false);
    }
  }

  const card = (id: string, body?: ReactNode) => (
    <BotSetupCard key={id} id={id} chosen={id === chosen} playable={Boolean(scanner.get(id))}
      level={session.level} busy={busy} onChoose={onChooseSetup} onLevel={onLevel}
      templates={tpl.setup(id)} templatesError={tpl.error} templateBusy={playing}
      onPlayTemplate={(s, t) => void play(s, t)} onOpenParams={setEditing}>
      {body}
    </BotSetupCard>
  );
  const inPlay = tpl.setup(chosen)?.templates.find(t => t.in_play) ?? null;

  return (
    <section className="bots-card bots-strats" data-testid="bots-strategies">
      <header className="bots-card__head">
        <h3>{BOTS_STRATEGIES_TITLE} <span className="bots-source">{BOTS_STRATEGIES_SOURCE}</span></h3>
        <span className="bots-card__sub">{BOTS_STRATEGIES_SUB}</span>
      </header>
      {tpl.payload?.error ? <p className="bots-hero__error" role="alert">{tpl.payload.error}</p> : null}
      {playError ? <p className="bots-hero__error" role="alert" data-testid="bots-template-play-error">{playError}</p> : null}

      <div className="bots-strat-grid">
        {card(chosen, chosen === BOT_SETUP_FIRST_PULLBACK ? (
          <>
            {inPlay ? (
              <div className="bots-tape" aria-label="Tape gate">
                {tapeLines(inPlay.values).map(([verdict, text]) => (
                  <span key={verdict} className="bots-tape__v" title={TAPE_VERDICT_TITLES[verdict]}>
                    <b className={`bots-vbadge bots-vbadge--${verdict}`}>{verdict.toUpperCase()}</b> {text}
                  </span>
                ))}
              </div>
            ) : null}
            <BotReadout readout={session.readout} />
          </>
        ) : undefined)}
        {others.map(id => card(id))}
      </div>

      <button type="button" className="bots-addsetup" data-testid="bots-add-setup" onClick={() => void explainAddSetup()}>
        <b>+ {BOTS_ADD_SETUP_LABEL}</b>
        <span>{BOTS_ADD_SETUP_HINT}</span>
      </button>

      <BotTemplateEditor open={editing != null} setup={editing ? tpl.setup(editing) : null}
        maxPerSetup={tpl.payload?.max_per_setup ?? 6} onClose={() => setEditing(null)} onApply={tpl.apply} />
    </section>
  );
}

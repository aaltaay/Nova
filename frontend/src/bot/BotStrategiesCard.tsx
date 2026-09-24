/**
 * The operator's playbook on the Bots page (ADR 027, ADR 029, ADR 031): a card per
 * setup, each with its own small scanner on the live board, its own level, its
 * template in play and its own read-out. The chosen setup carries the bot's level
 * and draws its tape gate and read-out in full; every other setup with a scanner
 * is Off (watches and scores in silence) or Eyes (proposes), several at once.
 * Choosing a setup, its level and its template are real controls; every parameter
 * opens in the template editor. Nothing here places an order.
 */
import { useState, type ReactNode } from 'react';
import { BackendReloadButton } from '../components/BackendReloadButton';
import {
  BOT_SCANNER_SETUP_IDS,
  BOT_SETUP_FIRST_PULLBACK,
  BOT_SETUP_IDS,
  BOT_STALE_BACKEND_BANNER,
} from '../constantGroups/bot';
import {
  BOTS_ADD_SETUP_CLOSE,
  BOTS_ADD_SETUP_COPY,
  BOTS_ADD_SETUP_HINT,
  BOTS_ADD_SETUP_LABEL,
  BOTS_ADD_SETUP_MESSAGE,
  BOTS_CATALOGUE_PATH,
  BOTS_STRATEGIES_SOURCE,
  BOTS_STRATEGIES_SUB,
  BOTS_STRATEGIES_SUB_TIP,
  BOTS_STRATEGIES_TITLE,
  BOTS_TAPE_GATE_HEAD,
} from '../constantGroups/bots_page';
import { TAPE_VERDICT_TIPS } from '../constantGroups/setups';
import {
  recordedEmptyText,
  setupTypeOf,
  simBoardLine,
  simBoardTip,
  useSetupsBoard,
  type SetupRow,
} from '../setups';
import { confirmApp } from '../ux/appDialogApi';
import { canReloadLocalBackend } from '../utils/startLocalApi';
import { tipProps } from '../ux/hoverTip';
import { BotReadout } from './BotReadout';
import { BotSetupCard } from './BotSetupCard';
import { BotTemplateEditor } from './BotTemplateEditor';
import { tapeLines } from './templateFormat';
import { playTemplate } from './templatesApi';
import type { BotSession } from './types';
import { useSetupTemplates } from './useSetupTemplates';
import './botTemplates.css';
import './botSetupScanner.css';

interface Props {
  session: BotSession;
  busy: boolean;
  onChooseSetup: (id: string) => void;
  /** The chosen setup's level: the session's (the arming path, useBotArm). */
  onLevel: (level: number) => void;
  /** Another setup's Off / Eyes (ADR 031). */
  onSetupLevel: (id: string, level: number) => void;
  /** "Open board ↗": Watchlist › Setups filtered to the setup. */
  onOpenBoard: (id: string) => void;
  onOpenSymbol: (symbol: string) => void;
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

function bySetup(rows: readonly SetupRow[]): Map<string, SetupRow[]> {
  const out = new Map<string, SetupRow[]>();
  for (const r of rows) {
    const id = setupTypeOf(r);
    const list = out.get(id);
    if (list) list.push(r);
    else out.set(id, [r]);
  }
  return out;
}

export function BotStrategiesCard({ session, busy, onChooseSetup, onLevel, onSetupLevel, onOpenBoard, onOpenSymbol }: Props) {
  const chosen = session.setup || BOT_SETUP_FIRST_PULLBACK;
  const infos = new Map((session.setups ?? []).map(s => [s.id, s]));
  const levelsKnown = (session.setups ?? []).some(s => s.level !== undefined) || session.setup_levels != null;
  // An API older than ADR 031 lists setups without a level and runs the first pullback only: this
  // build's other scanners are not missing, they are not loaded. Say so, with the reload.
  const staleApi = !levelsKnown && (session.setups?.length ?? 0) > 0;
  const staleSetup = (id: string) => staleApi && BOT_SCANNER_SETUP_IDS.includes(id) && !infos.get(id)?.scanner;
  const others = BOT_SETUP_IDS.filter(id => id !== chosen);
  const tpl = useSetupTemplates();
  const stream = useSetupsBoard();
  const board = stream?.board ?? null;
  const allRows = board?.rows ?? [];
  const rows = bySetup(allRows);
  const summaries = new Map((board?.setups ?? []).map(s => [s.id, s]));
  const [editing, setEditing] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [playError, setPlayError] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

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

  const levelOf = (id: string): number => {
    if (id === chosen) return session.level;
    return infos.get(id)?.level ?? session.setup_levels?.[id] ?? summaries.get(id)?.level ?? 0;
  };
  const setLevel = (id: string, n: number) => {
    if (id === chosen) onLevel(n);
    else onSetupLevel(id, n);
  };

  const card = (id: string, body?: ReactNode) => (
    <BotSetupCard key={id} id={id} chosen={id === chosen} playable={Boolean(infos.get(id)?.scanner)} stale={staleSetup(id)}
      level={levelOf(id)} levelsKnown={levelsKnown} busy={busy} onChoose={onChooseSetup} onLevel={setLevel}
      templates={tpl.setup(id)} templatesError={tpl.error} templateBusy={playing}
      onPlayTemplate={(s, t) => void play(s, t)} onOpenParams={setEditing}
      summary={summaries.get(id) ?? null} rows={rows.get(id) ?? []} allRows={allRows}
      connected={Boolean(stream?.connected)} seeding={board?.seeding ?? 0} emptyText={recordedEmptyText(board)}
      hovered={hovered} onHover={setHovered} onOpenBoard={onOpenBoard} onOpenSymbol={onOpenSymbol}>
      {body}
    </BotSetupCard>
  );
  const inPlay = tpl.setup(chosen)?.templates.find(t => t.in_play) ?? null;
  const chosenPlays = Boolean(infos.get(chosen)?.scanner);

  return (
    <section className="bots-card bots-strats" data-testid="bots-strategies">
      <header className="bots-card__head">
        <h3>{BOTS_STRATEGIES_TITLE} <span className="bots-source">{BOTS_STRATEGIES_SOURCE}</span></h3>
        <span className="bots-card__sub" {...tipProps(BOTS_STRATEGIES_SUB_TIP, BOTS_STRATEGIES_TITLE)}>{BOTS_STRATEGIES_SUB}</span>
      </header>
      {staleApi ? (
        <div className="bots-stale" role="status" data-testid="bots-stale-backend">
          <p>{BOT_STALE_BACKEND_BANNER}</p>
          {canReloadLocalBackend() ? <BackendReloadButton /> : null}
        </div>
      ) : null}
      {board?.source === 'sim' ? (
        <p className={`bots-simline bots-simline--${board.replay?.kind ?? 'capture'}`} role="status"
          data-testid="bots-sim-line" {...tipProps(simBoardTip(board), 'Sim · the cards follow the playhead')}>
          {simBoardLine(board)}
        </p>
      ) : null}
      {tpl.payload?.error ? <p className="bots-hero__error" role="alert">{tpl.payload.error}</p> : null}
      {playError ? <p className="bots-hero__error" role="alert" data-testid="bots-template-play-error">{playError}</p> : null}

      <div className="bots-strat-grid">
        {card(chosen, chosenPlays ? (
          <>
            {inPlay ? (
              <div className="bots-tape" aria-label={BOTS_TAPE_GATE_HEAD}>
                <span className="bots-tape__head">{BOTS_TAPE_GATE_HEAD}</span>
                {tapeLines(inPlay.values).map(([verdict, text]) => (
                  <span key={verdict} className="bots-tape__v"
                    {...tipProps(TAPE_VERDICT_TIPS[verdict] ?? verdict, `${verdict.toUpperCase()} · the tape gate`)}>
                    <b className={`bots-vbadge bots-vbadge--${verdict}`}>{verdict.toUpperCase()}</b> {text}
                  </span>
                ))}
              </div>
            ) : null}
            <BotReadout setup={chosen} readout={session.readout} required={session.readout_required} />
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

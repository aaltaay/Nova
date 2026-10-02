/**
 * The operator's playbook on the Bots page (ADR 027, ADR 029, ADR 031, ADR 042): a card
 * per setup, each with its own small scanner on the live board, its own Off / Eyes /
 * Strategy under the bot's master level, its template in play, its tape gate and its
 * own read-out. There is no chosen setup: every setup at Strategy may be traded once
 * the bot is active, and the master level caps them all. Every parameter opens in the
 * template editor. Nothing here places an order.
 */
import { useState } from 'react';
import { BackendReloadButton } from '../components/BackendReloadButton';
import { BOT_SCANNER_SETUP_IDS, BOT_SETUP_IDS, BOT_SETUP_LABELS, BOT_SETUP_NEXT, BOT_STALE_BACKEND_BANNER } from '../constantGroups/bot';
import {
  BOTS_ADD_SETUP_CLOSE,
  BOTS_ADD_SETUP_COPY,
  BOTS_ADD_SETUP_HINT,
  BOTS_ADD_SETUP_LABEL,
  BOTS_ADD_SETUP_MESSAGE,
  BOTS_CATALOGUE_PATH,
  BOTS_STRATEGIES_ANCHOR,
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
import { effectiveLevel, levelName, masterLevel, ownLevel } from './botLevels';
import { botOn } from './botSwitch';
import { BotSetupCard } from './BotSetupCard';
import { BotTemplateEditor } from './BotTemplateEditor';
import { tapeLines } from './templateFormat';
import { playTemplate } from './templatesApi';
import type { SetupTemplates } from './templateTypes';
import type { BotSession } from './types';
import { useSetupTemplates } from './useSetupTemplates';
import './botTemplates.css';
import './botSetupScanner.css';

interface Props {
  session: BotSession;
  busy: boolean;
  /** A setup's own Off / Eyes / Strategy (ADR 042): PATCH {setup_levels: {id: n}}. */
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

/** A setup without a scanner, on hover: why it cannot watch yet and what unblocks it. */
function noScannerTip(id: string): string {
  const next = BOT_SETUP_NEXT[id];
  return next ? [next.head, next.why, `Unblocks when: ${next.unblock}`].join('\n') : 'No scanner yet.';
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

/** The setup's tape gate in its template in play's own numbers. */
function TapeGate({ templates }: { templates: SetupTemplates | null }) {
  const inPlay = templates?.templates.find(t => t.id === templates.in_play) ?? null;
  if (!inPlay) return null;
  return (
    <div className="bots-tape" aria-label={BOTS_TAPE_GATE_HEAD}>
      <span className="bots-tape__head">{BOTS_TAPE_GATE_HEAD}</span>
      {tapeLines(inPlay.values).map(([verdict, text]) => (
        <span key={verdict} className="bots-tape__v"
          {...tipProps(TAPE_VERDICT_TIPS[verdict] ?? verdict, `${verdict.toUpperCase()} · the tape gate`)}>
          <b className={`bots-vbadge bots-vbadge--${verdict}`}>{verdict.toUpperCase()}</b> {text}
        </span>
      ))}
    </div>
  );
}

export function BotStrategiesCard({ session, busy, onSetupLevel, onOpenBoard, onOpenSymbol }: Props) {
  const infos = new Map((session.setups ?? []).map(s => [s.id, s]));
  const levelsKnown = (session.setups ?? []).some(s => s.level !== undefined) || session.setup_levels != null;
  // An API older than ADR 031 lists setups without a level and runs the first pullback only: this
  // build's other scanners are not missing, they are not loaded. Say so, with the reload.
  const staleApi = !levelsKnown && (session.setups?.length ?? 0) > 0;
  const staleSetup = (id: string) => staleApi && BOT_SCANNER_SETUP_IDS.includes(id) && !infos.get(id)?.scanner;
  const master = levelName(masterLevel(session));
  const active = botOn(session);
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

  return (
    <section className="bots-card bots-strats" id={BOTS_STRATEGIES_ANCHOR} data-testid="bots-strategies">
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
        {BOT_SETUP_IDS.filter(id => Boolean(infos.get(id)?.scanner) || staleSetup(id)).map(id => {
          const templates = tpl.setup(id);
          return (
            <BotSetupCard key={id} id={id} playable={Boolean(infos.get(id)?.scanner)} stale={staleSetup(id)}
              own={ownLevel(session, id) ?? 0} effective={effectiveLevel(session, id) ?? 0} masterName={master}
              botActive={active} levelsKnown={levelsKnown} busy={busy} onLevel={onSetupLevel}
              templates={templates} templatesError={tpl.error} templateBusy={playing}
              onPlayTemplate={(s, t) => void play(s, t)} onOpenParams={setEditing} onApplyTemplates={tpl.apply}
              summary={summaries.get(id) ?? null} rows={rows.get(id) ?? []} allRows={allRows}
              connected={Boolean(stream?.connected)} seeding={board?.seeding ?? 0} emptyText={recordedEmptyText(board)}
              hovered={hovered} onHover={setHovered} onOpenBoard={onOpenBoard} onOpenSymbol={onOpenSymbol}>
              <TapeGate templates={templates} />
            </BotSetupCard>
          );
        })}
      </div>

      {BOT_SETUP_IDS.some(id => !infos.get(id)?.scanner && !staleSetup(id)) ? (
        <p className="bots-noscan-line" data-testid="bots-noscan-line">
          Not watching yet:{' '}
          {BOT_SETUP_IDS.filter(id => !infos.get(id)?.scanner && !staleSetup(id)).map((id, i) => (
            <span key={id} {...tipProps(noScannerTip(id), BOT_SETUP_LABELS[id] ?? id)}>
              {i ? ' · ' : ''}<b>{BOT_SETUP_LABELS[id] ?? id}</b>
            </span>
          ))}
          . Point at one for why it does not watch yet and what unblocks it.
        </p>
      ) : null}

      <button type="button" className="bots-addsetup" data-testid="bots-add-setup" onClick={() => void explainAddSetup()}>
        <b>+ {BOTS_ADD_SETUP_LABEL}</b>
        <span>{BOTS_ADD_SETUP_HINT}</span>
      </button>

      <BotTemplateEditor open={editing != null} setup={editing ? tpl.setup(editing) : null}
        maxPerSetup={tpl.payload?.max_per_setup ?? 6} onClose={() => setEditing(null)} onApply={tpl.apply} />
    </section>
  );
}

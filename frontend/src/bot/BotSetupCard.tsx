/**
 * One setup of the operator's playbook, with its own small scanner (ADR 027, ADR
 * 029, ADR 031): a radio to choose it, its own Off / Eyes / Strategy, a status line
 * saying what it is doing right now, the template in play, the names nearest their
 * trigger, today's funnel and its read-out. A setup without a scanner says what is
 * missing and what unblocks it. Every chip explains itself on hover
 * (ux/hoverTip.ts); every locked control says why (ux/whyTip.ts).
 */
import type { ReactNode } from 'react';
import {
  BOT_CHOSEN_BADGE,
  BOT_LEVEL_LABELS,
  BOT_NO_SCANNER_TITLE,
  BOT_SETUP_BLURBS,
  BOT_SETUP_LABELS,
  BOT_SETUP_LEVEL_CHIPS,
  BOT_SETUP_LEVEL_TIPS,
  BOT_SETUP_NEXT,
  BOT_SETUP_STRATEGY_WHY,
} from '../constantGroups/bot';
import {
  BOTS_BUSY_WHY,
  BOTS_FUNNEL_TIP,
  BOTS_FUNNEL_TODAY,
  BOTS_NO_SCANNER_UNBLOCK_HEAD,
  BOTS_NO_SCANNER_WHY_HEAD,
  BOTS_SCAN_FOOT,
  BOTS_SCAN_FOOT_TIP,
  BOTS_SCANNER_MAX_ROWS,
  BOTS_SETUP_NO_LEVELS_WHY,
  BOTS_SETUP_PICK_TIP,
  BOTS_SETUP_PICK_TITLE,
  BOTS_STATUS_NOT_CONNECTED,
  BOTS_STATUS_SEEDING,
  BOTS_STATUS_WATCHING,
  BOTS_TEMPLATE_LABEL,
  BOTS_TEMPLATE_LOADING_WHY,
  BOTS_TEMPLATE_NO_PARAMS_WHY,
  BOTS_TEMPLATE_PARAMS,
  BOTS_TEMPLATE_PICK_TITLE,
  BOTS_TEMPLATE_RULES_TIP,
  BOTS_TEMPLATE_SAVING_WHY,
  BOTS_TEMPLATE_UNREAD_WHY,
} from '../constantGroups/bots_page';
import {
  SETUP_OPEN_BOARD,
  SETUP_OPEN_BOARD_TIP,
  SETUP_STATUS_TIPS,
  SETUP_WINDOW_TIP,
} from '../constantGroups/setups';
import { funnelSteps, windowWords, type SetupRow, type SetupSummary } from '../setups';
import { tipProps } from '../ux/hoverTip';
import { BotResearchLine, BotReadoutLine } from './BotReadout';
import { BotSetupScanner } from './BotSetupScanner';
import { ruleLines, ruleSummary } from './templateFormat';
import type { SetupTemplates } from './templateTypes';

const LEVELS = [0, 1, 2] as const;

interface Props {
  id: string;
  chosen: boolean;
  /** The setup has a live scanner, so it may be chosen and levelled. */
  playable: boolean;
  /** This setup's level: the session's for the chosen setup, its own Off / Eyes for the others. */
  level: number;
  /** The API keeps a level per setup (ADR 031); false on an older one. */
  levelsKnown: boolean;
  busy: boolean;
  onChoose: (id: string) => void;
  onLevel: (id: string, level: number) => void;
  /** This setup's templates (ADR 029); null while they load or when they did not. */
  templates: SetupTemplates | null;
  templatesError?: string | null;
  /** A template write (put in play) is in flight. */
  templateBusy?: boolean;
  onPlayTemplate?: (setupId: string, templateId: string) => void;
  onOpenParams?: (setupId: string) => void;
  /** The live board's summary for this setup (ADR 031); null without a scanner or a board. */
  summary: SetupSummary | null;
  rows: readonly SetupRow[];
  allRows: readonly SetupRow[];
  connected: boolean;
  seeding: number;
  hovered: string | null;
  onHover: (symbol: string | null) => void;
  onOpenBoard: (id: string) => void;
  onOpenSymbol: (symbol: string) => void;
  /** The chosen setup's tape gate and full read-out. */
  children?: ReactNode;
}

function templateWhy(t: SetupTemplates | null, error: string | null | undefined, busy: boolean): string | null {
  if (!t) return error ? BOTS_TEMPLATE_UNREAD_WHY(error) : BOTS_TEMPLATE_LOADING_WHY;
  if (t.catalogue.groups.length === 0) return BOTS_TEMPLATE_NO_PARAMS_WHY;
  return busy ? BOTS_TEMPLATE_SAVING_WHY : null;
}

function levelWhy(n: number, p: Pick<Props, 'playable' | 'busy' | 'chosen' | 'levelsKnown'>): string | null {
  if (!p.playable) return BOT_NO_SCANNER_TITLE;
  if (p.busy) return BOTS_BUSY_WHY;
  if (p.chosen) return null;
  if (!p.levelsKnown) return BOTS_SETUP_NO_LEVELS_WHY;
  return n >= 2 ? BOT_SETUP_STRATEGY_WHY : null;
}

function nameTip(id: string, chosen: boolean, playable: boolean): string {
  const blurb = BOT_SETUP_BLURBS[id] ?? '';
  if (!playable) return `${blurb}\n\n${BOT_SETUP_NEXT[id]?.head ?? BOT_NO_SCANNER_TITLE.replace(/ -- /g, ' — ')}`;
  if (chosen) {
    return `${blurb}\n\nThe chosen setup: it carries the bot's level, Nova's bot trades it at Strategy on Paper and Sim, and its read-out gates Strategy on Live.`;
  }
  return `${blurb}\n\n${BOTS_SETUP_PICK_TIP}`;
}

function StatusLine({ level, summary, connected, seeding }: {
  level: number;
  summary: SetupSummary | null;
  connected: boolean;
  seeding: number;
}) {
  const win = windowWords(summary);
  const lvl = (level > 2 ? 2 : level < 0 ? 0 : level) as 0 | 1 | 2;
  const silent = lvl >= 1 && summary != null && !summary.proposing;
  return (
    <div className="bots-strat__status" data-testid="bots-setup-status">
      <span className={`bots-live-dot${connected ? ' is-on' : ''}`} aria-hidden="true" />
      <span {...tipProps(connected ? SETUP_STATUS_TIPS.watching : SETUP_STATUS_TIPS.disconnected)}>
        {connected ? BOTS_STATUS_WATCHING(summary?.counts.watching ?? 0) : BOTS_STATUS_NOT_CONNECTED}
      </span>
      {win ? <span className={`bots-strat__win bots-strat__win--${summary?.window.state}`} {...tipProps(SETUP_WINDOW_TIP)}>{` · ${win}`}</span> : null}
      {connected && seeding > 0 ? <span {...tipProps(SETUP_STATUS_TIPS.seeding)}>{` · ${BOTS_STATUS_SEEDING(seeding)}`}</span> : null}
      <span className={`bots-lvlchip bots-lvlchip--${lvl}`} data-testid="bots-setup-level-chip"
        {...tipProps(`${BOT_SETUP_LEVEL_TIPS[lvl]}${silent ? '\nThis desk is a replay: nothing proposes live from it.' : ''}`, BOT_LEVEL_LABELS[lvl])}>
        {BOT_SETUP_LEVEL_CHIPS[lvl]}
      </span>
    </div>
  );
}

function NotWatching({ id }: { id: string }) {
  const next = BOT_SETUP_NEXT[id];
  return (
    <>
      <div className="bots-strat__status bots-strat__status--off" data-testid="bots-setup-status">
        <span className="bots-live-dot" aria-hidden="true" />
        <span>{next?.head ?? BOT_NO_SCANNER_TITLE}</span>
      </div>
      {next ? (
        <div className="bots-noscan" data-testid={`bots-noscan-${id}`}>
          <p><b>{BOTS_NO_SCANNER_WHY_HEAD}</b> {next.why}</p>
          <p><b>{BOTS_NO_SCANNER_UNBLOCK_HEAD}</b> {next.unblock}</p>
        </div>
      ) : null}
    </>
  );
}

function Funnel({ id, summary }: { id: string; summary: SetupSummary | null }) {
  const steps = funnelSteps(id, summary?.counts);
  if (!steps.length) return null;
  return (
    <div className="bots-funnel" data-testid={`bots-funnel-${id}`}>
      <span className="bots-funnel__today" {...tipProps(BOTS_FUNNEL_TIP, BOTS_FUNNEL_TODAY)}>{BOTS_FUNNEL_TODAY}</span>
      {steps.map((s, i) => (
        <span key={s.key} className="bots-funnel__step">
          {i > 0 ? <i aria-hidden="true">{i < 4 ? '→' : '·'}</i> : null}
          <span {...tipProps(s.tip, `${s.n} ${s.word}`)}><b>{s.n}</b> {s.word}</span>
        </span>
      ))}
    </div>
  );
}

export function BotSetupCard(props: Props) {
  const {
    id, chosen, playable, level, busy, onChoose, onLevel, templates, templatesError = null, templateBusy = false,
    onPlayTemplate, onOpenParams, summary, rows, allRows, connected, seeding, hovered, onHover, onOpenBoard,
    onOpenSymbol, children,
  } = props;
  const shown = (level > 2 ? 2 : level < 0 ? 0 : level) as 0 | 1 | 2;
  const pickWhy = !playable ? BOT_NO_SCANNER_TITLE : busy ? BOTS_BUSY_WHY : null;
  const label = BOT_SETUP_LABELS[id] ?? id;
  const inPlay = templates?.templates.find(t => t.id === templates.in_play) ?? null;
  const lines = inPlay ? ruleLines(id, inPlay.values) : [];
  const summaryText = inPlay ? ruleSummary(id, inPlay.values) : '';
  const nParams = templates?.catalogue.groups.reduce((n, g) => n + g.params.length, 0) ?? 0;
  const tplWhy = templateWhy(templates, templatesError, templateBusy);
  const paramsWhy = templates ? (nParams === 0 ? BOTS_TEMPLATE_NO_PARAMS_WHY : null) : tplWhy;
  const rulesTip = lines.length ? BOTS_TEMPLATE_RULES_TIP(lines.map(([k, v]) => `${k}: ${v}`).join('\n')) : '';
  return (
    <article className={`bots-strat${chosen ? ' bots-strat--chosen' : ''}${playable ? '' : ' bots-strat--noscan'}`}
      data-testid={`bots-setup-${id}`}>
      <div className="bots-strat__head">
        <label className="bots-strat__pick">
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
          <b {...tipProps(nameTip(id, chosen, playable), label)}>{label}</b>
        </label>
        {chosen ? <span className="bots-badge">★ {BOT_CHOSEN_BADGE}</span> : null}
        <span className="bots-levels" role="radiogroup" aria-label={`${label} level`}>
          {LEVELS.map(n => {
            const why = levelWhy(n, props);
            return (
              <button
                key={n}
                type="button"
                role="radio"
                aria-checked={shown === n}
                className={`bots-levels__opt${shown === n ? ' is-on' : ''}`}
                data-testid={`bots-setup-level-${id}-${n}`}
                disabled={why != null}
                data-why={why ?? undefined}
                {...(why ? {} : tipProps(BOT_SETUP_LEVEL_TIPS[n], `${BOT_LEVEL_LABELS[n]} · ${label}`))}
                onClick={() => { if (shown !== n) onLevel(id, n); }}
              >
                {BOT_LEVEL_LABELS[n]}
              </button>
            );
          })}
        </span>
      </div>

      {playable ? <StatusLine level={shown} summary={summary} connected={connected} seeding={seeding} /> : <NotWatching id={id} />}

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
        {summaryText || rulesTip ? (
          <span className="bots-strat__rule" data-testid={`bots-setup-rules-${id}`} {...tipProps(rulesTip, `${label} · rules`)}>
            {summaryText || lines[0]?.[1]}
          </span>
        ) : null}
        <button type="button" className="bots-linkbtn" data-testid={`bots-setup-params-${id}`}
          disabled={paramsWhy != null} data-why={paramsWhy ?? undefined} onClick={() => onOpenParams?.(id)}>
          {BOTS_TEMPLATE_PARAMS(nParams)}
        </button>
      </div>

      {playable ? (
        <>
          <BotSetupScanner setup={id} rows={rows} allRows={allRows} connected={connected}
            onOpenSymbol={onOpenSymbol} hovered={hovered} onHover={onHover} />
          <div className="bots-strat__foot">
            {rows.length ? (
              <span {...tipProps(BOTS_SCAN_FOOT_TIP)}>{BOTS_SCAN_FOOT(Math.min(rows.length, BOTS_SCANNER_MAX_ROWS), rows.length)}</span>
            ) : <span />}
            <button type="button" className="bots-linkbtn" data-testid={`bots-setup-board-${id}`}
              onClick={() => onOpenBoard(id)} {...tipProps(SETUP_OPEN_BOARD_TIP)}>
              {SETUP_OPEN_BOARD}
            </button>
          </div>
          <Funnel id={id} summary={summary} />
        </>
      ) : null}

      {children ?? (playable ? <BotReadoutLine setup={id} readout={inPlay?.readout} /> : null)}
      <BotResearchLine setup={id} />
    </article>
  );
}

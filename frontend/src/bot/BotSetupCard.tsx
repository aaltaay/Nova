/**
 * One setup of the operator's playbook, with its own small scanner (ADR 027, ADR 029,
 * ADR 031, ADR 042): its own Off / Eyes / Strategy under the bot's master level (what
 * it may do now is the lower of the two, and the card says when it is capped), a
 * status line saying what it is doing right now, the template in play, the names
 * nearest their trigger, today's funnel, its tape gate and its read-out. A setup
 * without a scanner says only why it can't watch yet and what unblocks it -- no
 * template, no parameters, no level. Every chip explains itself on hover
 * (ux/hoverTip.ts); every locked control says why (ux/whyTip.ts).
 */
import type { ReactNode } from 'react';
import {
  BOT_STRATEGY_LEVEL_LABELS as BOT_LEVEL_LABELS,
  BOT_NO_SCANNER_TITLE,
  BOT_SETUP_BLURBS,
  BOT_SETUP_CAPPED_TIP,
  BOT_SETUP_LABELS,
  BOT_SETUP_LEVEL_CHIP_WAITING,
  BOT_SETUP_LEVEL_CHIPS,
  BOT_SETUP_LEVEL_TIPS,
  BOT_SETUP_LEVEL_WAITING_TIP,
  BOT_SETUP_NEXT,
  BOT_STALE_BACKEND_STATUS,
  BOT_STALE_BACKEND_TEMPLATE,
  BOT_STALE_BACKEND_WHY,
  botSetupCapped,
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
  BOTS_STATUS_NOT_CONNECTED,
  BOTS_STATUS_NOT_RECORDED,
  BOTS_STATUS_NOT_RECORDED_TIP,
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
import { clampLevel } from './botLevels';
import { BotReadoutLine, BotResearchLine } from './BotReadout';
import { BotSetupScanner } from './BotSetupScanner';
import { BotStrategyRules } from './BotStrategyRules';
import { ruleLines, ruleSummary } from './templateFormat';
import type { SetupTemplates } from './templateTypes';

const LEVELS = [0, 1, 2] as const;

interface Props {
  id: string;
  /** The setup has a live scanner, so it can be levelled. */
  playable: boolean;
  /** This build has the setup's scanner but the backend answering is older and does not run it:
   *  the card says the backend needs a reload instead of "No scanner yet". */
  stale?: boolean;
  /** Its own switch: 0 Off, 1 Eyes, 2 Strategy. */
  own: number;
  /** What it may do now: min(master, own). */
  effective: number;
  /** The master level's name, for the capped note ("Eyes"). */
  masterName: string;
  /** The bot is active on this venue: a setup at Strategy proposes like Eyes until it is. */
  botActive: boolean;
  /** The API keeps a level per setup; false on an older one. */
  levelsKnown: boolean;
  busy: boolean;
  onLevel: (id: string, level: number) => void;
  /** This setup's templates (ADR 029); null while they load or when they did not. */
  templates: SetupTemplates | null;
  templatesError?: string | null;
  /** A template write (put in play) is in flight. */
  templateBusy?: boolean;
  onPlayTemplate?: (setupId: string, templateId: string) => void;
  onOpenParams?: (setupId: string) => void;
  /** A strategy row's bot rules were saved (ADR 044): the setup's templates as the backend answered them. */
  onApplyTemplates?: (next: SetupTemplates) => void;
  /** The live board's summary for this setup (ADR 031); null without a board. */
  summary: SetupSummary | null;
  rows: readonly SetupRow[];
  allRows: readonly SetupRow[];
  connected: boolean;
  seeding: number;
  hovered: string | null;
  onHover: (symbol: string | null) => void;
  onOpenBoard: (id: string) => void;
  onOpenSymbol: (symbol: string) => void;
  /** An empty scanner's words at a recorded moment in Sim ("Nothing forming at 08:07:02 ET."). */
  emptyText?: string | null;
  /** The setup's tape gate. */
  children?: ReactNode;
}

function templateWhy(t: SetupTemplates | null, error: string | null | undefined, busy: boolean, stale: boolean): string | null {
  if (!t) return stale ? BOT_STALE_BACKEND_WHY : error ? BOTS_TEMPLATE_UNREAD_WHY(error) : BOTS_TEMPLATE_LOADING_WHY;
  if (t.catalogue.groups.length === 0) return BOTS_TEMPLATE_NO_PARAMS_WHY;
  return busy ? BOTS_TEMPLATE_SAVING_WHY : null;
}

function levelWhy(p: Pick<Props, 'busy' | 'levelsKnown' | 'stale'>): string | null {
  if (p.stale) return BOT_STALE_BACKEND_WHY;
  if (p.busy) return BOTS_BUSY_WHY;
  return p.levelsKnown ? null : BOTS_SETUP_NO_LEVELS_WHY;
}

function StatusLine({ effective, own, masterName, botActive, summary, connected, seeding }: {
  effective: 0 | 1 | 2;
  own: 0 | 1 | 2;
  masterName: string;
  botActive: boolean;
  summary: SetupSummary | null;
  connected: boolean;
  seeding: number;
}) {
  const silent = effective >= 1 && summary != null && !summary.proposing;
  const unrecorded = connected && summary?.recorded === false;
  const win = unrecorded ? '' : windowWords(summary);
  // ADR 044: On while the Bot is off alerts like Eyes until the Bot is on; only a legacy master below Eyes caps.
  const waiting = own === 2 && !botActive;
  const capped = !waiting && own > effective;
  const [words, tip] = !connected
    ? [BOTS_STATUS_NOT_CONNECTED, SETUP_STATUS_TIPS.disconnected]
    : unrecorded
      ? [BOTS_STATUS_NOT_RECORDED, BOTS_STATUS_NOT_RECORDED_TIP]
      : [BOTS_STATUS_WATCHING(summary?.counts.watching ?? 0), SETUP_STATUS_TIPS.watching];
  const chipTip = [
    waiting ? BOT_SETUP_LEVEL_WAITING_TIP : BOT_SETUP_LEVEL_TIPS[own],
    capped ? BOT_SETUP_CAPPED_TIP : '',
    silent ? 'This desk is a replay: nothing proposes live from it.' : '',
  ].filter(Boolean).join('\n');
  return (
    <div className="bots-strat__status" data-testid="bots-setup-status">
      <span className={`bots-live-dot${connected && !unrecorded ? ' is-on' : ''}`} aria-hidden="true" />
      <span {...tipProps(tip)}>{words}</span>
      {win ? <span className={`bots-strat__win bots-strat__win--${summary?.window.state}`} {...tipProps(SETUP_WINDOW_TIP)}>{` · ${win}`}</span> : null}
      {connected && seeding > 0 ? <span {...tipProps(SETUP_STATUS_TIPS.seeding)}>{` · ${BOTS_STATUS_SEEDING(seeding)}`}</span> : null}
      <span className={`bots-lvlchip bots-lvlchip--${effective}`} data-testid="bots-setup-level-chip"
        {...tipProps(chipTip, BOT_LEVEL_LABELS[own])}>
        {capped ? botSetupCapped(BOT_LEVEL_LABELS[own], masterName) : waiting ? BOT_SETUP_LEVEL_CHIP_WAITING : BOT_SETUP_LEVEL_CHIPS[own]}
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

function StaleStatus() {
  return (
    <div className="bots-strat__status bots-strat__status--stale" data-testid="bots-setup-status">
      <span className="bots-live-dot" aria-hidden="true" />
      <span>{BOT_STALE_BACKEND_STATUS}</span>
    </div>
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

/** Its own Off / Eyes / Strategy: every setup with a scanner may be at any of them (ADR 042). */
function LevelSwitch({ id, label, own, why, onLevel }: {
  id: string; label: string; own: 0 | 1 | 2; why: string | null; onLevel: (id: string, level: number) => void;
}) {
  return (
    <span className="bots-levels" role="radiogroup" aria-label={`${label} level`}>
      {LEVELS.map(n => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={own === n}
          className={`bots-levels__opt${own === n ? ' is-on' : ''}`}
          data-testid={`bots-setup-level-${id}-${n}`}
          disabled={why != null}
          data-why={why ?? undefined}
          {...(why ? {} : tipProps(BOT_SETUP_LEVEL_TIPS[n], `${BOT_LEVEL_LABELS[n]} · ${label}`))}
          onClick={() => { if (own !== n) onLevel(id, n); }}
        >
          {BOT_LEVEL_LABELS[n]}
        </button>
      ))}
    </span>
  );
}

export function BotSetupCard(props: Props) {
  const {
    id, playable, stale = false, own, effective, masterName, botActive, onLevel, templates, templatesError = null,
    templateBusy = false, onPlayTemplate, onOpenParams, onApplyTemplates, summary, rows, allRows, connected, seeding, hovered, onHover,
    onOpenBoard, onOpenSymbol, emptyText, children,
  } = props;
  const label = BOT_SETUP_LABELS[id] ?? id;
  const blurb = BOT_SETUP_BLURBS[id] ?? '';
  if (!playable && !stale) {
    // No scanner in this build: only why it can't watch yet and what unblocks it.
    return (
      <article className="bots-strat bots-strat--noscan" data-testid={`bots-setup-${id}`}>
        <div className="bots-strat__head">
          <b className="bots-strat__name" {...tipProps(`${blurb}\n\n${BOT_SETUP_NEXT[id]?.head ?? BOT_NO_SCANNER_TITLE}`, label)}>{label}</b>
        </div>
        <NotWatching id={id} />
        <BotResearchLine setup={id} />
      </article>
    );
  }
  const ownLevel = clampLevel(own);
  const shown = clampLevel(effective);
  const inPlay = templates?.templates.find(t => t.id === templates.in_play) ?? null;
  const lines = inPlay ? ruleLines(id, inPlay.values, inPlay.bot_window) : [];
  const summaryText = inPlay ? ruleSummary(id, inPlay.values) : '';
  const nParams = templates?.catalogue.groups.reduce((n, g) => n + g.params.length, 0) ?? 0;
  const tplWhy = templateWhy(templates, templatesError, templateBusy, stale);
  const paramsWhy = templates ? (nParams === 0 ? BOTS_TEMPLATE_NO_PARAMS_WHY : null) : tplWhy;
  const rulesTip = lines.length ? BOTS_TEMPLATE_RULES_TIP(lines.map(([k, v]) => `${k}: ${v}`).join('\n')) : '';
  return (
    <article className={`bots-strat${shown === 2 ? ' bots-strat--strategy' : ''}${stale ? ' bots-strat--stale' : ''}`}
      data-testid={`bots-setup-${id}`}>
      <div className="bots-strat__head">
        <b className="bots-strat__name" {...tipProps(stale ? `${blurb}\n\n${BOT_STALE_BACKEND_STATUS}.` : blurb, label)}>{label}</b>
        <LevelSwitch id={id} label={label} own={ownLevel} why={levelWhy(props)} onLevel={onLevel} />
      </div>

      {stale ? <StaleStatus /> : (
        <StatusLine effective={shown} own={ownLevel} masterName={masterName} botActive={botActive}
          summary={summary} connected={connected} seeding={seeding} />
      )}

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
            {!templates ? (
              <option value="">{stale ? BOT_STALE_BACKEND_TEMPLATE : templatesError ? 'did not load' : 'loading…'}</option>
            ) : null}
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

      {stale ? null : <BotStrategyRules setup={id} templates={templates} onApply={t => onApplyTemplates?.(t)} />}

      {stale ? null : (
        <>
          <BotSetupScanner setup={id} rows={rows} allRows={allRows} connected={connected}
            onOpenSymbol={onOpenSymbol} hovered={hovered} onHover={onHover} emptyText={emptyText} />
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
          {children}
          <BotReadoutLine setup={id} readout={inPlay?.readout} />
        </>
      )}
      <BotResearchLine setup={id} />
    </article>
  );
}

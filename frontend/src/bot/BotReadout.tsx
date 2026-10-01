/**
 * Every setup's read-out (Bot-Trading-Plan §2g, backend setup_scanner/readout.py, ADR
 * 042 G), from its template in play: the same pre-registered rule for each setup, on
 * its own rows. It measures whether the tape gate turns the setup into a winner. Nova's
 * bot trades Paper and Sim only and Live trading by a bot is not built, so passing it
 * unlocks nothing yet -- the card says so, and that it scores the backtest's exit while
 * the bot sells everything at target 1 with a 15-minute time stop, and how many of its
 * triggers fell inside the bot's window.
 */
import {
  BOT_READOUT_EXITS,
  BOT_READOUT_STATE_LABELS,
  BOT_READOUT_TIP,
  BOT_READOUT_WHAT,
  BOT_SETUP_LABELS,
  BOT_SETUP_RESEARCH,
  botReadoutInside,
} from '../constantGroups/bot';
import {
  BOTS_READOUT_GO_SHORT,
  BOTS_READOUT_GO_SO_FAR,
  BOTS_READOUT_NEEDS,
  BOTS_READOUT_SHORT,
  BOTS_READOUT_VS,
  BOTS_RESEARCH_BADGES,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import { fmtR } from './botsPageFormat';
import type { TemplateReadout } from './templateTypes';

function tone(v: number | null | undefined): string {
  return v == null ? '' : v > 0 ? ' is-up' : v < 0 ? ' is-down' : '';
}

function label(setup: string): string {
  return (BOT_SETUP_LABELS[setup] ?? setup).toLowerCase();
}

/** "Bars alone: failed" as a badge, then the rest of the research line. */
export function BotResearchLine({ setup }: { setup: string }) {
  const research = BOT_SETUP_RESEARCH[setup];
  if (!research) return null;
  return (
    <p className={`bots-strat__research bots-strat__research--${research.verdict}`} {...tipProps(research.text, 'What the research said')}>
      <span className="bots-rbadge">{BOTS_RESEARCH_BADGES[research.verdict] ?? research.verdict}</span> {research.detail}
    </p>
  );
}

/** A setup's read-out, from its template in play (templates API, ADR 029). */
export function BotReadoutLine({ setup, readout }: { setup: string; readout: TemplateReadout | null | undefined }) {
  if (!readout) return null;
  const min = readout.min_go ?? 50;
  const go = readout.go_triggered ?? 0;
  const pct = Math.max(0, Math.min(100, (100 * go) / (min || 50)));
  const vs = readout.go_avg_net_r != null || readout.control_avg_net_r != null;
  const w = readout.bot_window;
  return (
    <div className={`bots-readout bots-readout--line bots-readout--${readout.state}`} data-testid={`bots-setup-readout-${setup}`}
      {...tipProps(`${BOT_READOUT_TIP(label(setup))}${readout.reason ? `\nNow: ${readout.reason}` : ''}`, `${BOTS_READOUT_SHORT} · ${BOT_SETUP_LABELS[setup] ?? setup}`)}>
      <div className="bots-readout__head">
        <b>{BOTS_READOUT_SHORT}</b>
        <span className="bots-readout__state">{BOT_READOUT_STATE_LABELS[readout.state] ?? readout.state}</span>
        <span className="bots-readout__count"><b data-testid={`bots-readout-count-${setup}`}>{go} / {min}</b> {BOTS_READOUT_GO_SHORT}</span>
      </div>
      <div className="bots-readout__bar"><i style={{ width: `${pct}%` }} /></div>
      {vs ? (
        <div className="bots-readout__nums">
          <span>
            {BOTS_READOUT_GO_SO_FAR} <b className={tone(readout.go_avg_net_r)}>{fmtR(readout.go_avg_net_r)}</b>{' '}
            {BOTS_READOUT_VS} <b className={tone(readout.control_avg_net_r)}>{fmtR(readout.control_avg_net_r)}</b>
          </span>
          <span>{BOTS_READOUT_NEEDS(readout.min_net_r ?? 0.2)}</span>
        </div>
      ) : null}
      {w && w.triggered_inside != null ? (
        <p className="bots-readout__inside" data-testid={`bots-readout-inside-${setup}`}>
          {botReadoutInside(w.triggered_inside, w.go_triggered_inside ?? 0, w.start, w.end)}
        </p>
      ) : null}
      <p className="bots-readout__note" data-testid={`bots-readout-what-${setup}`}>{BOT_READOUT_WHAT}</p>
      <p className="bots-readout__note">{BOT_READOUT_EXITS}</p>
    </div>
  );
}

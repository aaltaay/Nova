/**
 * Every setup's read-out (Bot-Trading-Plan §2g, backend setup_scanner/readout.py,
 * ADR 031): the same pre-registered rule for each setup, on its own rows. The
 * chosen setup's is drawn in full -- it gates Strategy on Live -- and every other
 * card shows its template's read-out in one line. Both explain the rule on hover.
 */
import {
  BOT_READOUT_STATE_LABELS,
  BOT_READOUT_TIP,
  BOT_READOUT_TITLE,
  BOT_READOUT_WAIVED_NOTE,
  BOT_SETUP_LABELS,
  BOT_SETUP_RESEARCH,
} from '../constantGroups/bot';
import {
  BOTS_READOUT_GO_SHORT,
  BOTS_READOUT_GO_SO_FAR,
  BOTS_READOUT_SHORT,
  BOTS_READOUT_UNREPORTED,
  BOTS_READOUT_VS,
  BOTS_RESEARCH_BADGES,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import { fmtR, readoutProgress } from './botsPageFormat';
import type { TemplateReadout } from './templateTypes';
import type { BotReadout as Readout } from './types';

/** The element the hero's "not proven yet" chip scrolls to. */
export const BOTS_READOUT_ANCHOR = 'bots-readout';

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

/** The chosen setup's read-out in full. ``required`` is the session's ``readout_required`` (ADR 030). */
export function BotReadout({ setup, readout, required }: { setup: string; readout: Readout | undefined; required?: boolean }) {
  if (!readout) {
    return <div className="bots-readout" id={BOTS_READOUT_ANCHOR} data-testid="bots-readout">{BOTS_READOUT_UNREPORTED}</div>;
  }
  const min = readout.rules?.min_go ?? 50;
  const minR = readout.rules?.min_net_r ?? 0.2;
  return (
    <div className={`bots-readout bots-readout--${readout.state}`} id={BOTS_READOUT_ANCHOR} data-testid="bots-readout"
      {...tipProps(`${BOT_READOUT_TIP(label(setup))}\nNow: ${readout.reason}`, BOT_READOUT_TITLE)}>
      <div className="bots-readout__head">
        <b>{BOT_READOUT_TITLE}</b>
        <span className="bots-readout__state">{BOT_READOUT_STATE_LABELS[readout.state] ?? readout.state}</span>
        <span className="bots-readout__count">
          <b data-testid="bots-readout-count">{readout.go.triggered} / {min}</b> go setups triggered
        </span>
      </div>
      <div className="bots-readout__bar"><i style={{ width: `${readoutProgress(readout)}%` }} /></div>
      <div className="bots-readout__nums">
        <span>
          {BOTS_READOUT_GO_SO_FAR} <b className={tone(readout.go.avg_net_r)}>{fmtR(readout.go.avg_net_r)}</b>{' '}
          {BOTS_READOUT_VS} <b className={tone(readout.control.avg_net_r)}>{fmtR(readout.control.avg_net_r)}</b>
        </span>
        <span>needs &gt; +{minR.toFixed(2)}R and above blind / wait</span>
      </div>
      {required === false && !readout.passed ? (
        <p className="bots-readout__waived" data-testid="bots-readout-waived">{BOT_READOUT_WAIVED_NOTE}</p>
      ) : null}
    </div>
  );
}

/** Another setup's read-out in one line, from its template in play (templates API, ADR 029). */
export function BotReadoutLine({ setup, readout }: { setup: string; readout: TemplateReadout | null | undefined }) {
  if (!readout) return null;
  const min = readout.min_go ?? 50;
  const go = readout.go_triggered ?? 0;
  const pct = Math.max(0, Math.min(100, (100 * go) / (min || 50)));
  const vs = readout.go_avg_net_r != null || readout.control_avg_net_r != null;
  return (
    <div className={`bots-readout bots-readout--line bots-readout--${readout.state}`} data-testid={`bots-setup-readout-${setup}`}
      {...tipProps(`${BOT_READOUT_TIP(label(setup))}${readout.reason ? `\nNow: ${readout.reason}` : ''}`, `${BOTS_READOUT_SHORT} · ${BOT_SETUP_LABELS[setup] ?? setup}`)}>
      <div className="bots-readout__head">
        <b>{BOTS_READOUT_SHORT}</b>
        <span className="bots-readout__state">{BOT_READOUT_STATE_LABELS[readout.state] ?? readout.state}</span>
        <span className="bots-readout__count"><b>{go} / {min}</b> {BOTS_READOUT_GO_SHORT}</span>
      </div>
      <div className="bots-readout__bar"><i style={{ width: `${pct}%` }} /></div>
      {vs ? (
        <div className="bots-readout__nums">
          <span>
            {BOTS_READOUT_GO_SO_FAR} <b className={tone(readout.go_avg_net_r)}>{fmtR(readout.go_avg_net_r)}</b>{' '}
            {BOTS_READOUT_VS} <b className={tone(readout.control_avg_net_r)}>{fmtR(readout.control_avg_net_r)}</b>
          </span>
        </div>
      ) : null}
    </div>
  );
}

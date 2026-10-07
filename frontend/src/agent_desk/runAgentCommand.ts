/**
 * Run one agent command on this desk (ADR 050): a show -- the venue to the Sim when the plan says so, then
 * the Sim landed on the stock-day and parked, paused -- or a move of the playhead. Every step is reported to
 * the backend and said in the notice; a report that answers anything but `running` (a newer request replaced
 * this one) stops it. Nothing here places, stages or cancels an order.
 */
import { moveDeskToVenue } from '../ibkr';
import { LandingStopped, landSim, moveSim, type Landed, type LandingHooks } from '../sim';
import type { AgentCommand, AgentCommandStatus, AgentReport, ShowPlan } from './agentDeskApi';
import { AGENT_DESK_TEXT } from './agentDeskConstants';

export type AgentNoticeState = 'running' | 'done' | 'failed' | 'cancelled';
export interface AgentNotice { id: string; title: string; text: string; state: AgentNoticeState }

export interface RunDeps {
  openTab: (symbol: string) => void;
  report: (id: string, report: AgentReport) => Promise<AgentCommandStatus | null>;
  notice: (notice: AgentNotice) => void;
  moveVenue?: (venue: 'sim') => Promise<string | null>;
  land?: typeof landSim;
  move?: typeof moveSim;
}

const HHMM = /^\d{1,2}:\d{2}$/;

/** Where a show parked, in words: "5 min before the run", "at the high", "at 09:45". */
export function atWords(at: string): string {
  if (HHMM.test(at)) return `at ${at}`;
  return ({
    run: '5 min before the run', drop: '5 min before the drop', high: 'at the high', low: 'at the low',
    open: 'at the open', premarket: 'at 04:00',
  } as Record<string, string>)[at] ?? `at ${at}`;
}

function playheadEt(landed: Landed): string | null {
  const iso = landed.clock?.sim_time_et;
  const match = typeof iso === 'string' ? /T(\d{2}:\d{2}:\d{2})/.exec(iso) : null;
  return match ? match[1] : null;
}

function result(landed: Landed, extra: Record<string, unknown> = {}) {
  return {
    symbol: landed.symbol, date: landed.date, playhead_et: playheadEt(landed),
    paused: landed.clock?.paused ?? null,
    window: landed.window ? { start: landed.window.start, end: landed.window.end } : null, ...extra,
  };
}

function showDoneText(plan: ShowPlan, landed: Landed): string {
  const at = playheadEt(landed)?.slice(0, 5) ?? plan.park_et.slice(0, 5);
  return `Paused at ${at} ET, ${plan.park_words ?? atWords(plan.at)}`;
}

export async function runAgentCommand(command: AgentCommand, deps: RunDeps): Promise<void> {
  if (command.kind === 'unreadable') {
    await deps.report(command.id, { status: 'failed', error: command.error }).catch(() => null);
    return;
  }
  const title = `${command.plan.symbol} · ${command.plan.date}`;
  const say = (state: AgentNoticeState, text: string) => deps.notice({ id: command.id, title, text, state });
  const step: LandingHooks['step'] = async (name, text) => {
    say('running', text);
    return (await deps.report(command.id, { status: 'running', step: name, text })) === 'running';
  };
  const hooks: LandingHooks = { step, openTab: deps.openTab };
  try {
    if (command.kind === 'show') {
      if (command.plan.switch_venue) {
        if (!(await step('venue', 'Switching the desk to the Sim'))) throw new LandingStopped('replaced');
        const refused = await (deps.moveVenue ?? moveDeskToVenue)('sim');
        if (refused) throw new Error(refused);
      }
      const landed = await (deps.land ?? landSim)(command.plan, hooks);
      const text = showDoneText(command.plan, landed);
      say('done', text);
      await deps.report(command.id, { status: 'done', step: 'parked', text, result: result(landed, { at: command.plan.at }) });
      return;
    }
    const landed = await (deps.move ?? moveSim)(command.plan, hooks);
    const at = playheadEt(landed);
    const where = command.plan.target_words ? `, ${command.plan.target_words}` : '';
    const text = at ? `Playhead at ${at.slice(0, 5)} ET${where}${landed.clock?.paused ? ', paused' : ''}` : 'Done';
    say('done', text);
    await deps.report(command.id, { status: 'done', step: 'moved', text, result: result(landed) });
  } catch (error) {
    if (error instanceof LandingStopped) {
      say('cancelled', AGENT_DESK_TEXT.cancelled);
      return;
    }
    const message = error instanceof Error ? error.message : String(error);
    say('failed', message);
    await deps.report(command.id, { status: 'failed', error: message }).catch(() => null);
  }
}

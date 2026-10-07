/**
 * The main window listens for agent commands (ADR 050): a long poll, one command at a time, backing off when
 * Nova is restarting (a growing wait) or when its API has no agent endpoints for this desk (an older backend
 * or no API key: rarely). Stops when `signal` aborts.
 */
import { AgentDeskUnavailable, fetchNextCommand, reportCommand } from './agentDeskApi';
import {
  AGENT_DESK_RETRY_MAX_MS,
  AGENT_DESK_RETRY_MS,
  AGENT_DESK_UNAVAILABLE_RETRY_MS,
} from './agentDeskConstants';
import { runAgentCommand, type AgentNotice } from './runAgentCommand';

export interface ListenDeps {
  openTab: (symbol: string) => void;
  notice: (notice: AgentNotice) => void;
  next?: typeof fetchNextCommand;
  run?: typeof runAgentCommand;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

function sleepFor(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise(resolve => {
    const timer = window.setTimeout(done, ms);
    function done() {
      window.clearTimeout(timer);
      signal.removeEventListener('abort', done);
      resolve();
    }
    signal.addEventListener('abort', done, { once: true });
  });
}

export async function listenForAgentCommands(signal: AbortSignal, deps: ListenDeps): Promise<void> {
  const next = deps.next ?? fetchNextCommand;
  const run = deps.run ?? runAgentCommand;
  const sleep = deps.sleep ?? sleepFor;
  let retry = AGENT_DESK_RETRY_MS;
  while (!signal.aborted) {
    let command;
    try {
      command = await next(signal);
      retry = AGENT_DESK_RETRY_MS;
    } catch (error) {
      if (signal.aborted) return;
      await sleep(error instanceof AgentDeskUnavailable ? AGENT_DESK_UNAVAILABLE_RETRY_MS : retry, signal);
      retry = Math.min(retry * 2, AGENT_DESK_RETRY_MAX_MS);
      continue;
    }
    if (command && !signal.aborted) {
      try {
        await run(command, { openTab: deps.openTab, notice: deps.notice, report: reportCommand });
      } catch (error) {
        // A report that could not reach Nova: the backend fails the command on its own when it hears no more.
        console.warn('agent desk: a command ended without its last report', error);
      }
    }
  }
}

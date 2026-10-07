/**
 * The main window's half of the agent endpoints (ADR 050): take the next command (a long poll) and report
 * each step. A command is parsed at the boundary; anything unreadable is reported back as failed, never run.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import type { LandingWindow, SimLandingPlan, SimMovePlan } from '../sim';
import {
  AGENT_DESK_FETCH_TIMEOUT_MS,
  AGENT_DESK_NEXT_PATH,
  AGENT_DESK_POLL_WAIT_SEC,
  AGENT_DESK_REPORT_TIMEOUT_MS,
  AGENT_DESK_WINDOW_ID,
  agentDeskReportPath,
} from './agentDeskConstants';

export type AgentCommandStatus = 'queued' | 'running' | 'done' | 'failed' | 'expired' | 'cancelled';

export interface ShowPlan extends SimLandingPlan { at: string; park_et: string; park_words: string | null; switch_venue: boolean }
export interface MovePlan extends SimMovePlan { target_words: string | null }
export type AgentCommand =
  | { id: string; kind: 'show'; status: AgentCommandStatus; plan: ShowPlan }
  | { id: string; kind: 'move'; status: AgentCommandStatus; plan: MovePlan }
  | { id: string; kind: 'unreadable'; status: AgentCommandStatus; error: string };

export interface AgentReport { status: 'running' | 'done' | 'failed'; step?: string; text?: string; result?: unknown; error?: string }

/** The API answered but has no agent endpoints for this desk (an older backend, or no API key). */
export class AgentDeskUnavailable extends Error {}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0;

function parseWindow(raw: unknown): LandingWindow | null {
  if (!isObj(raw) || !isStr(raw.start) || !isStr(raw.end) || !isNum(raw.start_ts) || !isNum(raw.end_ts)) return null;
  return { start: raw.start, end: raw.end, start_ts: raw.start_ts, end_ts: raw.end_ts };
}

function parseWindows(raw: unknown): LandingWindow[] | null {
  if (!Array.isArray(raw)) return null;
  const out = raw.map(parseWindow);
  return out.every(Boolean) ? (out as LandingWindow[]) : null;
}

function parseShow(plan: Record<string, unknown>): ShowPlan | null {
  const window = parseWindow(plan.window);
  const fallbacks = parseWindows(plan.fallback_windows);
  if (!isStr(plan.symbol) || !isStr(plan.date) || !window || !fallbacks || !isNum(plan.park_ts)) return null;
  return {
    symbol: plan.symbol, date: plan.date, window, fallback_windows: fallbacks, park_ts: plan.park_ts,
    at: isStr(plan.at) ? plan.at : 'run', park_et: isStr(plan.park_et) ? plan.park_et : '',
    park_words: isStr(plan.park_words) ? plan.park_words : null,
    switch_venue: plan.switch_venue === true,
  };
}

function parseMove(plan: Record<string, unknown>): MovePlan | null {
  const window = plan.window == null ? null : parseWindow(plan.window);
  const fallbacks = parseWindows(plan.fallback_windows ?? []);
  if (!isStr(plan.symbol) || !isStr(plan.date) || !isNum(plan.loaded_start_ts) || fallbacks === null) return null;
  if (plan.window != null && !window) return null;
  return {
    symbol: plan.symbol, date: plan.date, loaded_start_ts: plan.loaded_start_ts, window, fallback_windows: fallbacks,
    target_ts: isNum(plan.target_ts) ? plan.target_ts : null,
    paused: typeof plan.paused === 'boolean' ? plan.paused : null,
    target_words: isStr(plan.target_words) ? plan.target_words : null,
  };
}

export function parseAgentCommand(raw: unknown): AgentCommand | null {
  if (!isObj(raw) || !isStr(raw.id)) return null;
  const status = (isStr(raw.status) ? raw.status : 'running') as AgentCommandStatus;
  const plan = isObj(raw.plan) ? raw.plan : null;
  const parsed = plan && raw.kind === 'show' ? parseShow(plan) : plan && raw.kind === 'move' ? parseMove(plan) : null;
  if (raw.kind === 'show' && parsed) return { id: raw.id, kind: 'show', status, plan: parsed as ShowPlan };
  if (raw.kind === 'move' && parsed) return { id: raw.id, kind: 'move', status, plan: parsed as MovePlan };
  return { id: raw.id, kind: 'unreadable', status, error: `the desk cannot read a ${String(raw.kind)} command` };
}

async function withTimeout(path: string, init: RequestInit, ms: number, signal?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = window.setTimeout(abort, ms);
  try {
    return await novaFetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

/** The next command for this window, now its own; null when none came within the poll's wait. */
export async function fetchNextCommand(signal?: AbortSignal): Promise<AgentCommand | null> {
  const query = `?wait=${AGENT_DESK_POLL_WAIT_SEC}&window_id=${AGENT_DESK_WINDOW_ID}`;
  const res = await withTimeout(`${AGENT_DESK_NEXT_PATH}${query}`, {}, AGENT_DESK_FETCH_TIMEOUT_MS, signal);
  if (res.status === 404 || res.status === 401 || res.status === 403 || res.status === 503) {
    throw new AgentDeskUnavailable(`agent endpoints unavailable (${res.status})`);
  }
  if (!res.ok) throw new Error(`agent poll failed (${res.status})`);
  const body: unknown = await res.json().catch(() => null);
  if (!isObj(body) || body.command == null) return null;
  return parseAgentCommand(body.command);
}

/** Report a step; the command's status after it (`cancelled` when a newer request replaced it), null if gone. */
export async function reportCommand(id: string, report: AgentReport): Promise<AgentCommandStatus | null> {
  const res = await withTimeout(agentDeskReportPath(id), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(report),
  }, AGENT_DESK_REPORT_TIMEOUT_MS);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`agent report failed (${res.status})`);
  const body: unknown = await res.json().catch(() => null);
  const command = isObj(body) && isObj(body.command) ? body.command : null;
  return command && isStr(command.status) ? (command.status as AgentCommandStatus) : null;
}

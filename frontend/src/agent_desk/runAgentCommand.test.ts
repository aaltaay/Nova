/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { LandingStopped, type Landed } from '../sim';
import { parseAgentCommand, type AgentCommand, type AgentReport } from './agentDeskApi';
import { atWords, runAgentCommand, type AgentNotice } from './runAgentCommand';

const W = { start: '09:00', end: '11:15', start_ts: 100, end_ts: 8200 };
const SHOW = {
  id: 'c1', kind: 'show', status: 'running',
  plan: { symbol: 'MSGY', date: '2026-09-25', at: 'run', park_et: '09:29:00', park_ts: 1840, window: W,
    fallback_windows: [], switch_venue: true },
};
const LANDED: Landed = { symbol: 'MSGY', date: '2026-09-25', window: W,
  clock: { sim: true, paused: true, sim_time_et: '2026-09-25T09:29:00-04:00' } };

function deps(over: Record<string, unknown> = {}) {
  const reports: AgentReport[] = [];
  const notices: AgentNotice[] = [];
  return {
    reports, notices,
    openTab: vi.fn(),
    report: vi.fn(async (_id: string, r: AgentReport) => { reports.push(r); return r.status === 'running' ? 'running' : r.status; }),
    notice: (n: AgentNotice) => { notices.push(n); },
    moveVenue: vi.fn(async () => null),
    land: vi.fn(async () => LANDED),
    move: vi.fn(async () => LANDED),
    ...over,
  };
}

const show = () => parseAgentCommand(SHOW) as AgentCommand;

describe('parseAgentCommand', () => {
  it('reads a show and a move and turns anything else into an unreadable command', () => {
    expect(show()).toMatchObject({ kind: 'show', plan: { symbol: 'MSGY', switch_venue: true, park_ts: 1840 } });
    const move = parseAgentCommand({ id: 'c2', kind: 'move', status: 'running',
      plan: { symbol: 'MSGY', date: '2026-09-25', target_ts: 500, paused: null, loaded_start_ts: 100, window: null,
        fallback_windows: [] } });
    expect(move).toMatchObject({ kind: 'move', plan: { target_ts: 500, window: null } });
    expect(parseAgentCommand({ id: 'c3', kind: 'show', plan: { symbol: 'X' } })?.kind).toBe('unreadable');
    expect(parseAgentCommand({ kind: 'show' })).toBeNull();
  });
});

describe('runAgentCommand', () => {
  it('switches to the Sim when the plan says so, lands, and reports done with where the playhead is', async () => {
    const d = deps();
    await runAgentCommand(show(), d);
    expect(d.moveVenue).toHaveBeenCalledWith('sim');
    expect(d.land).toHaveBeenCalledOnce();
    const done = d.reports.at(-1);
    expect(done).toMatchObject({ status: 'done', step: 'parked', result: { playhead_et: '09:29:00', paused: true } });
    expect(d.notices.at(-1)).toMatchObject({ state: 'done', title: 'MSGY · 2026-09-25' });
    expect(d.notices.at(-1)?.text).toContain('09:29 ET, 5 min before the run');
  });

  it('a venue refusal or a landing error is reported failed, in its own words', async () => {
    const refused = deps({ moveVenue: vi.fn(async () => 'Nova did not answer') });
    await runAgentCommand(show(), refused);
    expect(refused.land).not.toHaveBeenCalled();
    expect(refused.reports.at(-1)).toMatchObject({ status: 'failed', error: 'Nova did not answer' });
    const broken = deps({ land: vi.fn(async () => { throw new Error('the import took too long'); }) });
    await runAgentCommand(show(), broken);
    expect(broken.notices.at(-1)).toMatchObject({ state: 'failed', text: 'the import took too long' });
  });

  it('a newer request stops it quietly: no failure is reported', async () => {
    const d = deps({ land: vi.fn(async () => { throw new LandingStopped('replaced'); }) });
    await runAgentCommand(show(), d);
    expect(d.reports.some(r => r.status === 'failed')).toBe(false);
    expect(d.notices.at(-1)?.state).toBe('cancelled');
  });

  it('an unreadable command is reported failed and never run', async () => {
    const d = deps();
    await runAgentCommand({ id: 'c9', kind: 'unreadable', status: 'running', error: 'cannot read' }, d);
    expect(d.reports).toEqual([{ status: 'failed', error: 'cannot read' }]);
    expect(d.land).not.toHaveBeenCalled();
  });

  it('says where it parked in words', () => {
    expect(atWords('run')).toBe('5 min before the run');
    expect(atWords('high')).toBe('at the high');
    expect(atWords('09:45')).toBe('at 09:45');
  });
});

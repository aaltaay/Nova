import { describe, expect, it } from 'vitest';
import {
  BACKEND_NOTICE_RESTART_LABEL,
  backendNotice,
  confirmText,
  needsConfirm,
  restartRisk,
} from './backendNoticeModel';
import { readUpdateView, type EngineSync } from './updateView';

const OWNER = 'C:\\Users\\op\\github\\Nova';
const attached: EngineSync = { owner: OWNER, attachedToOwner: true, running: null, last: null, auto: null };
const elsewhere: EngineSync = { ...attached, attachedToOwner: false };
// Nova brought it along once and it is still behind: the button is the operator's.
const left: EngineSync = { ...attached, auto: { state: 'left', holds: [], reason: '' } };

describe('the backend notice (one version, 2026-09-30)', () => {
  it('brings a backend behind the desk along by itself: no button, nothing to put off (operator ask 2026-10-13)', () => {
    for (const running of [null, 'pull', 'restart'] as const) {
      const model = backendNotice({ backend: 'v1025', checkout: 'v1027', desk: 'v1029', engine: { ...attached, running } });
      expect(model).toMatchObject({ action: null, byItself: true, holds: [] });
      expect(model?.text).toBe('Nova is updating the backend to v1029…');
      expect(model?.hint).toBe('It ran v1025. It is back in about half a minute, and the desk reconnects by itself.');
    }
  });

  it('says what holds Nova\'s own restart, beside Update backend now', () => {
    const holds = ['Paper position MNDR 100: Nova stops watching it while the backend restarts'];
    const engine: EngineSync = { ...attached, auto: { state: 'waiting', holds, reason: '' } };
    const model = backendNotice({ backend: 'v1025', checkout: 'v1027', desk: 'v1029', engine });
    expect(model).toMatchObject({ action: 'update', actionLabel: 'Update backend now', byItself: false, holds });
    expect(model?.hint).toBe('Nova updates and restarts it by itself once nothing is open. Waiting for:');
  });

  it('offers one action when Nova could not bring it along, whatever its checkout holds (no restart-then-pull)', () => {
    const why = backendNotice({
      backend: 'v1025',
      checkout: 'v1025',
      desk: 'v1029',
      engine: { ...attached, auto: { state: 'left', holds: [], reason: 'Not updated: the checkout is on feature/x, not master' } },
    });
    expect(why?.hint).toBe('Not updated: the checkout is on feature/x, not master');
    for (const checkout of ['v1025', 'v1027', null]) {
      const model = backendNotice({ backend: 'v1025', checkout, desk: 'v1029', engine: left });
      expect(model).toMatchObject({ action: 'update', actionLabel: 'Update backend to v1029' });
      expect(model?.text).toBe('Backend v1025 is behind this desk (v1029).');
      expect(model?.hint).toBe(`Nova runs as one version: this brings ${OWNER} to v1029 and restarts the backend.`);
    }
  });

  it('offers the desk update for a backend ahead of it (2026-09-30: desk v1050, backend v1051)', () => {
    const model = backendNotice({ backend: 'v1051', checkout: 'v1051', desk: 'v1050', engine: attached });
    expect(model).toMatchObject({ action: 'desk', actionLabel: 'Update desk to v1051' });
    expect(model?.text).toBe('Backend v1051 is ahead of this desk (v1050).');
  });

  it('restarts a backend from another checkout that holds newer code, and says what to do otherwise', () => {
    const restart = backendNotice({ backend: 'v1025', checkout: 'v1027', desk: 'v1029', engine: elsewhere });
    expect(restart).toMatchObject({ action: 'restart', actionLabel: BACKEND_NOTICE_RESTART_LABEL });
    expect(restart?.hint).toBe('Its checkout holds v1027: a restart loads it.');
    const stuck = backendNotice({ backend: 'v1025', checkout: 'v1025', desk: 'v1029', engine: elsewhere });
    expect(stuck?.action).toBeNull();
    expect(stuck?.hint).toMatch(/^It does not run from your Nova checkout: bring its checkout to v1029/);
  });

  it('says nothing when the backend runs the desk\'s version, or is unknown', () => {
    expect(backendNotice({ backend: 'v1029', checkout: 'v1029', desk: 'v1029', engine: attached })).toBeNull();
    expect(backendNotice({ backend: null, checkout: null, desk: 'v1029', engine: attached })).toBeNull();
  });

  it('comes back after Later when a revision changes', () => {
    const a = backendNotice({ backend: 'v1025', checkout: 'v1027', desk: 'v1029', engine: attached });
    const b = backendNotice({ backend: 'v1025', checkout: 'v1028', desk: 'v1029', engine: attached });
    expect(a?.key).not.toBe(b?.key);
  });

  it('reads the restart check: nothing open is one click, anything else is listed', () => {
    const safe = restartRisk({ schema_version: 1, safe: true, open: [], unknown: [] });
    expect(needsConfirm('restart', safe)).toBe(false);
    expect(needsConfirm('update', safe)).toBe(false);
    expect(needsConfirm('desk', restartRisk(null))).toBe(false);
    const open = restartRisk({
      schema_version: 1,
      safe: false,
      open: [{ kind: 'recording', text: "Recording MSGY: a few seconds' gap, then it resumes on its own" }],
      unknown: [{ kind: 'ibkr', error: 'RuntimeError: cache unreadable' }],
    });
    expect(needsConfirm('restart', open)).toBe(true);
    expect(needsConfirm('update', open)).toBe(true);
    const text = confirmText('update', open, OWNER, 'v1029');
    expect(text).toContain(`Brings ${OWNER} to v1029 (fast-forward only)`);
    expect(text).toContain('- Recording MSGY');
    expect(text).toContain('- Could not read ibkr: RuntimeError: cache unreadable');
  });

  it('never reads a backend older than the check as safe', () => {
    const risk = restartRisk(null);
    expect(risk.safe).toBeNull();
    expect(needsConfirm('restart', risk)).toBe(true);
    expect(restartRisk({ detail: 'Not Found' }).safe).toBeNull();
  });

  it('parses the engine part of the update view', () => {
    const view = readUpdateView({
      schema_version: 1,
      installed: 'v1029',
      notice: null,
      whats_new: null,
      file_issue: null,
      engine: {
        owner: OWNER,
        attached_to_owner: true,
        running: 'pull',
        last: { at: 5, outcome: 'failed', text: 'Not pulled: the checkout is on feature/x, not master' },
        auto: { state: 'waiting', holds: ['The opening bell (09:25-09:45 ET)', 7], reason: '' },
      },
    });
    expect(view?.engine).toEqual({
      owner: OWNER,
      attachedToOwner: true,
      running: 'pull',
      last: { at: 5, outcome: 'failed', text: 'Not pulled: the checkout is on feature/x, not master' },
      auto: { state: 'waiting', holds: ['The opening bell (09:25-09:45 ET)'], reason: '' },
    });
    expect(readUpdateView({ schema_version: 1, installed: 'v1029' })?.engine).toBeNull();
  });
});

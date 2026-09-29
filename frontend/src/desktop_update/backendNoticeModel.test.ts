import { describe, expect, it } from 'vitest';
import {
  BACKEND_NOTICE_RESTART_LABEL,
  BACKEND_NOTICE_SYNC_LABEL,
  backendNotice,
  confirmText,
  needsConfirm,
  restartRisk,
} from './backendNoticeModel';
import { readUpdateView, type EngineSync } from './updateView';

const OWNER = 'C:\\Users\\op\\github\\Nova';
const attached: EngineSync = { owner: OWNER, attachedToOwner: true, running: null, last: null };

describe('the backend notice (ADR 038 amendment)', () => {
  it("offers a restart when the backend's checkout already holds the newer code (2026-09-29: v1025 on v1027)", () => {
    const model = backendNotice({ backend: 'v1025', checkout: 'v1027', desk: 'v1029', engine: attached });
    expect(model).toMatchObject({ action: 'restart', actionLabel: BACKEND_NOTICE_RESTART_LABEL });
    expect(model?.text).toBe('Backend v1025 runs older code than this desk (v1029).');
    expect(model?.hint).toBe('Its checkout holds v1027: a restart loads it.');
  });

  it('offers a pull when the checkout holds nothing newer and the desk can pull it', () => {
    const model = backendNotice({ backend: 'v1025', checkout: 'v1025', desk: 'v1029', engine: attached });
    expect(model).toMatchObject({ action: 'sync', actionLabel: BACKEND_NOTICE_SYNC_LABEL });
    // A backend not running from the remembered checkout: say what to do, offer nothing it cannot do.
    const elsewhere = backendNotice({
      backend: 'v1025', checkout: 'v1025', desk: 'v1029', engine: { ...attached, attachedToOwner: false },
    });
    expect(elsewhere?.action).toBeNull();
    expect(elsewhere?.hint).toMatch(/^Pull master in its checkout/);
  });

  it('says nothing when the backend is current, newer, or unknown', () => {
    expect(backendNotice({ backend: 'v1029', checkout: 'v1029', desk: 'v1029', engine: attached })).toBeNull();
    expect(backendNotice({ backend: 'v1030', checkout: 'v1030', desk: 'v1029', engine: attached })).toBeNull();
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
    // A pull always asks: it changes the checkout.
    expect(needsConfirm('sync', safe)).toBe(true);
    const open = restartRisk({
      schema_version: 1,
      safe: false,
      open: [{ kind: 'recording', text: "Recording MSGY: a few seconds' gap, then it resumes on its own" }],
      unknown: [{ kind: 'ibkr', error: 'RuntimeError: cache unreadable' }],
    });
    expect(needsConfirm('restart', open)).toBe(true);
    const text = confirmText('restart', open, OWNER);
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
      },
    });
    expect(view?.engine).toEqual({
      owner: OWNER,
      attachedToOwner: true,
      running: 'pull',
      last: { at: 5, outcome: 'failed', text: 'Not pulled: the checkout is on feature/x, not master' },
    });
    expect(readUpdateView({ schema_version: 1, installed: 'v1029' })?.engine).toBeNull();
  });
});

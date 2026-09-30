/**
 * The backend notice (ADR 038 amendment, operator ask 2026-09-29; one version, 2026-09-30): a strip
 * under the header, beside the update notice, while the backend runs another release than this desk.
 * One action closes the gap -- "Update backend to vNNN", "Update desk to vNNN" or, for a backend from
 * another checkout, "Restart backend now" -- after the desk asked the backend what a restart would
 * interrupt; nothing open goes at once, anything open is listed first. Later hides it until a
 * revision changes. It never takes keyboard focus, like the update notice. Words and decisions:
 * backendNoticeModel.ts.
 */
import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { confirmApp } from '../ux';
import {
  refreshBackendReleaseTag,
  useBackendCheckoutTag,
  useBackendReleaseTag,
} from '../utils/backendReleaseTag';
import { novaRendererReleaseTag } from '../utils/novaReleaseTag';
import { startLocalApi } from '../utils/startLocalApi';
import {
  BACKEND_RESTART_CHECK_PATH,
  backendNotice,
  confirmText,
  needsConfirm,
  restartRisk,
} from './backendNoticeModel';
import type { EngineSync, UpdateAction } from './updateView';

interface Props {
  engine: EngineSync;
  act: (action: UpdateAction) => void;
}

async function readRestartCheck(): Promise<unknown> {
  try {
    const res = await fetch(`${API_BASE_URL}${BACKEND_RESTART_CHECK_PATH}`, { cache: 'no-store' });
    return res.ok ? await res.json() : null;
  } catch (err) {
    console.warn('[nova] restart check unavailable', err);
    return null;
  }
}

export function BackendNotice({ engine, act }: Props) {
  const backend = useBackendReleaseTag();
  const checkout = useBackendCheckoutTag();
  const desk = novaRendererReleaseTag();
  const [later, setLater] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastAt = engine.last?.at ?? 0;

  // A pull or restart the main process finished: read the backend's revision now, not in a minute.
  useEffect(() => {
    if (lastAt) void refreshBackendReleaseTag();
  }, [lastAt]);

  const model = backendNotice({ backend, checkout, desk, engine });
  if (!model || model.key === later) return null;
  const running = engine.running;
  const working = busy || running !== null;
  const outcome = engine.last?.outcome === 'failed' ? engine.last.text : null;

  async function run() {
    if (working || !model?.action) return;
    if (model.action === 'desk') {
      act('check-update');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const risk = restartRisk(await readRestartCheck());
      if (needsConfirm(model.action, risk)) {
        const ok = await confirmApp({
          title: model.actionLabel,
          message: confirmText(model.action, risk, engine.owner, desk),
          confirmLabel: model.actionLabel,
          tone: 'warning',
        });
        if (!ok) return;
      }
      if (model.action === 'update') {
        act('backend-sync');
        return;
      }
      const result = await startLocalApi();
      if (!result.ok) setError(result.error);
      await refreshBackendReleaseTag();
    } finally {
      setBusy(false);
    }
  }

  const label = running === 'pull' ? 'Updating the checkout…' : running === 'restart' || busy ? 'Restarting…' : model.actionLabel;
  return (
    <div className="nova-update-notice" role="status" data-stage="backend" data-testid="backend-notice">
      <div className="nova-update-notice__row">
        <span className="nova-update-notice__mark" aria-hidden="true">
          ⟳
        </span>
        <span className="nova-update-notice__text">
          {model.text}
          <span className="nova-update-notice__hint"> {error ?? outcome ?? model.hint}</span>
        </span>
        <span className="nova-update-notice__actions">
          {model.action && (
            <button
              type="button"
              className="nova-update-notice__btn nova-update-notice__btn--primary"
              onClick={() => void run()}
              disabled={working}
              data-why={working ? 'The backend is restarting -- wait for it to come back' : undefined}
            >
              {label}
            </button>
          )}
          <button type="button" className="nova-update-notice__btn" onClick={() => setLater(model.key)} disabled={working}
            data-why={working ? 'Wait for the restart to finish' : undefined}>
            Later
          </button>
        </span>
      </div>
    </div>
  );
}

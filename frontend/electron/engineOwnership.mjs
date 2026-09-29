/**
 * ADR 038 startup policy for the packaged desk and the engine already on :8000.
 * Pure decisions and copy live here; sidecar.mjs owns probes and the dialog.
 */

/**
 * Whether an installed desk may adopt the engine already answering on :8000 without
 * asking. Called only after /api/health answered, so an unreadable identity (no
 * diagnostics, a timeout) is an owner Nova cannot prove -- ask, never spawn over it.
 */
export function packagedEngineDecision({ deskTag, engine } = {}) {
  if (!engine) return 'ask';
  if (engine.frozen === true && engine.release_tag && engine.release_tag === deskTag) return 'reuse';
  return 'ask';
}

function label(value, fallback) {
  const text = String(value ?? '').trim();
  return text || fallback;
}

/** Operator-facing explanation for a packaged desk that found a non-matching owner. */
export function ownershipPrompt({ deskTag, engine } = {}) {
  const desk = label(deskTag, 'this release');
  const backend = label(engine?.release_tag, 'an unknown release');
  const source = engine?.frozen
    ? 'another installed Nova release'
    : engine?.root
      ? `the checkout at ${engine.root}`
      : 'an engine whose owner Nova cannot prove';
  return {
    type: 'warning',
    title: 'Choose which Nova backend to use',
    message: `Nova ${desk} found backend ${backend} from ${source}.`,
    detail:
      'Installed Nova normally uses the matching backend bundled with the app. Stop the other Nova backend (and its watchdog, if running), then retry. Using it for this session may expose a version mismatch.',
    buttons: ['Retry with packaged backend', 'Use external backend this session', 'Exit Nova'],
    defaultId: 0,
    cancelId: 2,
    noLink: true,
  };
}

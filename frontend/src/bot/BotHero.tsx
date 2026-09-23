/**
 * The Bots page hero (approved mockup v4, ADR 027): the bot's state in one
 * sentence, the level as three segments, every gate the backend checks, and
 * Activate / Stop. It replaces the header's second row on this page. Level 2
 * arms first; Activate at Strategy waits on the first-pullback read-out.
 */
import { useState } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import {
  BOT_ACTIVATE_LABEL,
  BOT_API_KEY_HINT,
  BOT_API_KEY_SAVE,
  BOT_DEACTIVATE_LABEL,
  BOT_IN_CONTROL_LABEL,
  BOT_LEVEL_BLURBS,
  BOT_LEVEL_LABELS,
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
} from '../constantGroups/bot';
import { closedActivateGates, gateLine, heroSentence, playingLine } from './botsPageFormat';
import { useBotArm } from './useBotArm';

const LEVELS = [0, 1, 2] as const;

export function BotHero() {
  const {
    session, error, busy, stop, armed, level, display, live, activateBlocked, activateReason,
    showKeyField, onLevel, onControl, activate,
  } = useBotArm();
  const [keyDraft, setKeyDraft] = useState('');
  if (!session) return null;
  const gates = (session.gates ?? []).map(gateLine);
  const closed = closedActivateGates(session.gates);
  const clamped = (level > 2 ? 2 : level) as 0 | 1 | 2;
  const headline = display.looksActive ? BOT_STATE_ACTIVE : armed ? display.label : BOT_STATE_NOT_ACTIVE;

  return (
    <section
      className={`bots-hero${live ? ' bots-hero--live' : ''}${display.looksActive ? ' bots-hero--armed' : ''}`}
      data-testid="bots-hero"
    >
      <div className="bots-hero__main">
        <div className="bots-hero__state">
          <span className={`bots-dot${display.looksActive ? ' bots-dot--on' : ''}`} aria-hidden="true" />
          <h2 data-testid="bots-hero-state">{headline}</h2>
        </div>
        <p className="bots-hero__sentence">{heroSentence(session, closed.length)}</p>
        <p className="bots-hero__playing" data-testid="bots-hero-playing">{playingLine(session)}</p>
        <div className="bots-seg" role="radiogroup" aria-label="Level">
          {LEVELS.map(n => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={clamped === n}
              className={`bots-seg__opt${clamped === n ? ' is-on' : ''}`}
              data-testid={`bots-level-${n}`}
              disabled={busy}
              onClick={() => { if (clamped !== n) void onLevel(n); }}
            >
              <b><span className="bots-seg__lvl">L{n}</span>{BOT_LEVEL_LABELS[n]}</b>
              <small>{BOT_LEVEL_BLURBS[n]}</small>
            </button>
          ))}
        </div>
        <ul className="bots-gates" data-testid="bots-gates">
          {gates.map(g => (
            <li key={g.id} className={g.ok ? 'is-ok' : g.stage === 'activate' ? 'is-closed' : 'is-fire'}
              data-testid={`bots-gate-${g.id}`}>
              <span className="bots-gates__mark" aria-hidden="true">{g.ok ? '✓' : '✕'}</span>
              {g.text}
            </li>
          ))}
        </ul>
      </div>
      <div className="bots-hero__actions">
        {armed ? (
          <button type="button" className="bots-btn" data-testid="bots-stop" disabled={busy} onClick={() => void stop()}>
            {BOT_DEACTIVATE_LABEL}
          </button>
        ) : (
          <button
            type="button"
            className="bots-btn bots-btn--primary"
            data-testid="bots-activate"
            disabled={busy || activateBlocked}
            title={activateReason ?? undefined}
            onClick={() => { if (!activateBlocked) void activate(); }}
          >
            ▶ {BOT_ACTIVATE_LABEL} bot
          </button>
        )}
        {!armed && level >= 2 && closed.length > 0 ? (
          <p className="bots-hero__hint" data-testid="bots-activate-hint">
            Clear the {closed.length} closed gate{closed.length === 1 ? '' : 's'} to enable
          </p>
        ) : null}
        {level >= 2 ? (
          <label className="bots-hero__check" data-testid="bots-in-control-label">
            <input
              type="checkbox"
              data-testid="bots-in-control"
              checked={armed}
              disabled={busy || (!armed && activateBlocked)}
              onChange={e => void onControl(e.target.checked)}
            />
            {BOT_IN_CONTROL_LABEL}
          </label>
        ) : null}
        {error ? <p className="bots-hero__error" data-testid="bots-error" role="alert">{error}</p> : null}
        {showKeyField ? (
          <form
            className="bots-hero__key"
            data-testid="bots-api-key"
            onSubmit={e => { e.preventDefault(); writeNovaApiKey(keyDraft); setKeyDraft(''); }}
          >
            <input type="password" autoComplete="off" value={keyDraft} aria-label={BOT_API_KEY_HINT}
              placeholder={BOT_API_KEY_HINT} onChange={e => setKeyDraft(e.target.value)} />
            <button type="submit" className="bots-btn" disabled={!keyDraft.trim()}>{BOT_API_KEY_SAVE}</button>
          </form>
        ) : null}
      </div>
    </section>
  );
}

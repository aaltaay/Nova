/**
 * IBKR's three Level 2 lines on one row (ADR 071): one per lane -- yours, Claude's seat's and the bots' -- each
 * with its stock, whether its Level 2 and Time & Sales lines are up and whether Nova records it; then the setup on
 * the bots' lane and the setups waiting for it. Read every few seconds while the page shows. Read-only: nothing
 * here moves a lane (yours follows the stock you open in front, Claude's the seat, the bots' the setups a bot may buy).
 */
import { useCallback, useEffect, useState } from 'react';
import { BOT_SETUP_LABELS } from '../constantGroups/bot';
import { AUTO_RECORD_WHY_WORDS, LANE_OWNER_WORDS } from '../capture';
import { LANE_OWNERS, type BotsLaneSetup, type Lane, type LaneOwner, type LanesView } from '../ibkr';
import { etTime } from './botWhen';
import { fetchLanes } from './linesApi';

const LINES_POLL_MS = 5_000;

function linesWords(l: Lane): string {
  if (l.depth && l.tape) return 'Level 2 + Time & Sales';
  if (l.depth) return 'Level 2, no Time & Sales';
  if (l.tape) return 'Time & Sales, no Level 2';
  return 'opening its lines';
}

function slotWords(owner: LaneOwner, l: Lane): string {
  const who = LANE_OWNER_WORDS[owner];
  if (!l.symbol) return `${who} · empty`;
  return `${who} · ${linesWords(l)}${l.recording ? ' · recording' : ''}${l.since ? ` · since ${etTime(l.since)}` : ''}`;
}

/** "AISP's first pullback (near its trigger)". */
function setupWords(s: BotsLaneSetup): string {
  const label = s.setup ? (BOT_SETUP_LABELS[s.setup] ?? s.setup.replace(/_/g, ' ')).toLowerCase() : 'setup';
  const why = s.why ? AUTO_RECORD_WHY_WORDS[s.why] ?? s.why : null;
  return `${s.symbol}'s ${label}${why ? ` (${why})` : ''}`;
}

export function BotLinesCard() {
  const [view, setView] = useState<LanesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setView(await fetchLanes());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), LINES_POLL_MS);
    return () => clearInterval(t);
  }, [load]);
  const used = view ? new Set(LANE_OWNERS.map(o => view[o].symbol).filter(Boolean)).size : null;
  const bots = view?.bots;
  return (
    <section className="bots-card bots-lines" data-testid="bots-lines">
      <div className="bots-lines__head">
        <h3>Level 2 lines <span className="bots-source">{used != null ? `${used} of 3` : '…'}</span></h3>
        <span className="bots-card__sub">One per lane: yours, Claude&apos;s and the bots&apos;. Nova reads the tape only where it holds both.</span>
      </div>
      <div className="bots-lines__row">
        {LANE_OWNERS.map(owner => {
          const l = view?.[owner] ?? null;
          return (
            <div key={owner} className={`bots-lines__slot${owner === 'you' && l?.symbol ? ' is-front' : ''}${l?.symbol ? '' : ' is-free'}`}
              data-testid={`bots-line-${owner}`}>
              <b>{l?.symbol ?? 'empty'}</b>
              <small>{l ? slotWords(owner, l) : LANE_OWNER_WORDS[owner]}</small>
              {l?.error && owner !== 'bots' ? <small className="is-bad">{l.error}</small> : null}
            </div>
          );
        })}
        <div className="bots-lines__loans" data-testid="bots-lines-bots">
          {bots?.symbol ? (
            <span>Bots: {setupWords({ symbol: bots.symbol, setup: bots.setup, why: bots.why })}</span>
          ) : view ? <span>No setup a bot may buy now: the bots&apos; lane is empty.</span> : null}
          {bots?.waiting.length ? (
            <span className="bots-muted" data-testid="bots-lines-waiting">Waiting: {bots.waiting.map(setupWords).join(', ')}</span>
          ) : null}
          {bots?.error ? <span className="is-bad">{bots.error}</span> : null}
          {error ? <span className="is-bad">{error}</span> : view ? null : <span>Reading who holds the lines…</span>}
        </div>
      </div>
    </section>
  );
}

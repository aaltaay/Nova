/**
 * The Global page (ADR 060; operator asks 2026-10-15 and 2026-10-20, mockup v2 approved): where the world's stock
 * money went -- each market's pressure from the real trades of its own index futures (or its US-listed ETF, named on
 * the row) and its index move, side by side, on a world map, by region, through the last 24 hours, and against each
 * other. Read-only: nothing here places an order; a country ETF's symbol opens the Trader. Every number is IBKR's.
 * Labels and scales follow the period of the board on screen, never the switch, so a period still loading is
 * never shown under another period's numbers.
 */
import { useState, type ReactNode } from 'react';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { AgreeChart } from './AgreeChart';
import {
  COLOR_BY_LABEL, GLOBAL_OFF, GLOBAL_OLD_API, GLOBAL_PERIODS, GLOBAL_REPLAY_NOTE, GLOBAL_SUBTITLE, GLOBAL_TITLE,
  GLOBAL_WAITING_HISTORY, GLOBAL_WAITING_LINES, MIXED_DEF, MOVE_DEF, PERIOD_LABEL, PRESSURE_DEF, SOURCES_DEF,
} from './constants';
import { ExchangeList } from './ExchangeList';
import { FollowTheSun } from './FollowTheSun';
import { etDay, etTime } from './format';
import { KpiStrip } from './KpiStrip';
import { useGlobalPrefs } from './prefs';
import type { ColorBy, GlobalBoard } from './types';
import { useGlobalBoard } from './useGlobalBoard';
import { WorldMap } from './WorldMap';
import './global.css';

export interface GlobalPageProps {
  onOpenTrader?: (symbol: string) => void;
}

function Seg<T extends string>({ value, options, labels, onPick, testId }: {
  value: T; options: readonly T[]; labels: Record<T, string>; onPick: (v: T) => void; testId: string;
}) {
  return (
    <div className="gb-seg" role="group" data-testid={testId}>
      {options.map((o) => (
        <button key={o} type="button" className={o === value ? 'is-on' : ''} aria-pressed={o === value}
          data-testid={`${testId}-${o}`} onClick={() => onPick(o)}>{labels[o]}</button>
      ))}
    </div>
  );
}

function Head({ board, children }: { board: GlobalBoard | null; children?: ReactNode }) {
  const open = board ? board.markets.filter((m) => m.session.state === 'open').length : 0;
  return (
    <div className="gb-head">
      <h2>{GLOBAL_TITLE}</h2>
      {board ? (
        <span className="gb-head__sub">
          {GLOBAL_SUBTITLE} · {etDay(board.generated_at)} · {etTime(board.generated_at)} ET · {open} of{' '}
          {board.markets.length} markets open
        </span>
      ) : null}
      {board?.replay_desk ? <span className="gb-pill">{GLOBAL_REPLAY_NOTE}</span> : null}
      {children}
    </div>
  );
}

export function GlobalPage({ onOpenTrader }: GlobalPageProps) {
  const sample = useSampleRoute();
  const [prefs, setPrefs] = useGlobalPrefs(!sample);
  const { data: board, error, unavailable } = useGlobalBoard(prefs.period);
  const [hovered, setHovered] = useState<string | null>(null);

  const switches = (
    <div className="gb-switches">
      <span className="gb-muted">Color the map by</span>
      <Seg<ColorBy> value={prefs.colorBy} options={['pressure', 'move']} labels={COLOR_BY_LABEL}
        onPick={(colorBy) => setPrefs({ ...prefs, colorBy })} testId="global-color-by" />
      <Seg value={prefs.period} options={GLOBAL_PERIODS} labels={PERIOD_LABEL}
        onPick={(period) => setPrefs({ ...prefs, period })} testId="global-period" />
    </div>
  );

  if (unavailable || !board || !board.enabled) {
    const words = unavailable ? GLOBAL_OLD_API : board && !board.enabled ? GLOBAL_OFF : error ?? 'Reading the world …';
    return (
      <div className="gb-page" data-testid="global-page">
        <Head board={null}>{switches}</Head>
        <p className="gb-wait" role="status">{words}</p>
      </div>
    );
  }

  const ibkr = board.sources.find((s) => s.id === 'ibkr');
  const waiting = board.budget.waiting === 'history' ? GLOBAL_WAITING_HISTORY
    : board.budget.waiting === 'lines' ? GLOBAL_WAITING_LINES : null;
  return (
    <div className="gb-page" data-testid="global-page">
      <Head board={board}>{switches}</Head>
      {error ? <p className="gb-stale" role="status">{error} -- showing the last good answer.</p> : null}
      {ibkr && ibkr.ok === false ? <p className="gb-stale" role="status">IBKR: {ibkr.error}</p> : null}
      {board.loading ? <p className="gb-wait" role="status">Reading each market from IBKR, last in line …</p> : null}
      {waiting ? <p className="gb-note" role="status">{waiting}</p> : null}
      {board.period !== prefs.period ? (
        <p className="gb-note" role="status" data-testid="global-period-loading">
          Loading {PERIOD_LABEL[prefs.period]} -- showing {PERIOD_LABEL[board.period]} until it answers.
        </p>
      ) : null}
      <KpiStrip read={board.read} world={board.world} regions={board.regions} />
      <div className="gb-main">
        <div className="gb-left">
          <section className="gb-card">
            <div className="gb-card__head">
              <h3>World map</h3>
              <span className="gb-muted">bubble = money traded · colour = {COLOR_BY_LABEL[prefs.colorBy].toLowerCase()} · dashed ring = open now</span>
              <span className="gb-legend">
                <i className="is-up" />{prefs.colorBy === 'pressure' ? 'Buyers more eager' : 'Index up'}
                <i className="is-down" />{prefs.colorBy === 'pressure' ? 'Sellers more eager' : 'Index down'}
              </span>
            </div>
            <WorldMap markets={board.markets} colorBy={prefs.colorBy} period={board.period} now={board.generated_at}
              hovered={hovered} onHover={setHovered} />
          </section>
          <div className="gb-bottom">
            <section className="gb-card">
              <div className="gb-card__head">
                <h3>Follow the sun</h3>
                <span className="gb-muted">pressure per hour, the last 24 hours, ET</span>
              </div>
              <FollowTheSun sun={board.sun} />
            </section>
            <section className="gb-card">
              <div className="gb-card__head">
                <h3>Do they agree?</h3>
                <span className="gb-muted">pressure against the index move</span>
              </div>
              <AgreeChart markets={board.markets} />
            </section>
          </div>
        </div>
        <section className="gb-card gb-side">
          <div className="gb-card__head">
            <h3>By exchange</h3>
            <span className="gb-muted">ranked by pressure · {PERIOD_LABEL[board.period]}</span>
          </div>
          <ExchangeList markets={board.markets} period={board.period} hovered={hovered} onHover={setHovered}
            onOpenTrader={onOpenTrader} />
          <div className="gb-defs">
            <p>{PRESSURE_DEF}</p>
            <p>{MOVE_DEF}</p>
            <p><span className="gb-flag">≠</span> {MIXED_DEF}</p>
            <p>{SOURCES_DEF}</p>
          </div>
        </section>
      </div>
    </div>
  );
}

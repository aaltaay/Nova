/**
 * The Global page (ADR 060; operator asks 2026-10-15 and 2026-10-20, mockup v2 approved): where the world's stock
 * money went -- each market's pressure from the real trades of its own index futures (or its US-listed ETF, named on
 * the row) and its index move, side by side, on a world map, by region, through the last 24 hours, and against each
 * other. Read-only: nothing here places an order; a country ETF's symbol opens the Trader. Every number is IBKR's.
 * Labels and scales follow the period of the board on screen, never the switch, so a period still loading is
 * never shown under another period's numbers. The page fills the window and never scrolls (ADR 060 amendment):
 * its notes share one line in the head, and the definitions open from "How to read".
 */
import { useState, type ReactNode } from 'react';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { AgreeChart } from './AgreeChart';
import {
  COLOR_BY_LABEL, GLOBAL_HOW_TO_READ, GLOBAL_OFF, GLOBAL_OLD_API, GLOBAL_PERIODS, GLOBAL_REPLAY_NOTE, GLOBAL_SUBTITLE,
  GLOBAL_TITLE, MIXED_DEF, MOVE_DEF, PERIOD_LABEL, PRESSURE_DEF, SIZE_DEF, SOURCES_DEF,
} from './constants';
import { ExchangeList } from './ExchangeList';
import { FollowTheSun } from './FollowTheSun';
import { KpiStrip } from './KpiStrip';
import { useGlobalPrefs } from './prefs';
import { statusNotes } from './status';
import type { ColorBy, GlobalBoard } from './types';
import { useGlobalBoard } from './useGlobalBoard';
import { WorldMap } from './WorldMap';
import { HowToRead, Seg, StatusLine, type Note } from '../world_board/controls';
import { etDay, etTime } from '../world_board/format';
import '../world_board/board.css';
import './global.css';

export interface GlobalPageProps {
  onOpenTrader?: (symbol: string) => void;
}

function Head({ board, notes, children }: { board: GlobalBoard | null; notes: Note[]; children?: ReactNode }) {
  const open = board ? board.markets.filter((m) => m.session.state === 'open').length : 0;
  return (
    <div className={`gb-head${notes.length ? ' has-notes' : ''}`}>
      <h2>{GLOBAL_TITLE}</h2>
      <span className="gb-head__tag">{GLOBAL_SUBTITLE}</span>
      {board ? (
        <span className="gb-head__sub">
          {etDay(board.generated_at)} · {etTime(board.generated_at)} ET · {open} of {board.markets.length} markets open
        </span>
      ) : null}
      {board?.replay_desk ? <span className="gb-pill">{GLOBAL_REPLAY_NOTE}</span> : null}
      <StatusLine notes={notes} prefix="global" />
      {children}
    </div>
  );
}

function Definitions() {
  return (
    <>
      <p>{PRESSURE_DEF}</p>
      <p>{MOVE_DEF}</p>
      <p><span className="gb-flag">≠</span> {MIXED_DEF}</p>
      <p>{SIZE_DEF}</p>
      <p>{SOURCES_DEF}</p>
    </>
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
        <Head board={null} notes={[]}>{switches}</Head>
        <p className="gb-wait" role="status">{words}</p>
      </div>
    );
  }

  return (
    <div className="gb-page" data-testid="global-page">
      <Head board={board} notes={statusNotes(board, prefs.period, error)}>{switches}</Head>
      <KpiStrip read={board.read} world={board.world} regions={board.regions} />
      <div className="gb-main">
        <div className="gb-left">
          <section className="gb-card gb-card--map">
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
            <HowToRead label={GLOBAL_HOW_TO_READ} prefix="global"><Definitions /></HowToRead>
          </div>
          <ExchangeList markets={board.markets} period={board.period} hovered={hovered} onHover={setHovered}
            onOpenTrader={onOpenTrader} />
        </section>
      </div>
    </div>
  );
}

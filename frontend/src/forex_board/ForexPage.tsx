/**
 * The Forex page (ADR 062; operator asks 2026-10-20, mockup v2 approved): the whole currency market's size -- the BIS
 * survey's, labelled, since forex has no exchange and no feed sees its total -- and what each of its 19 biggest
 * currencies did: its strength from IBKR's spot prices, and the public slice of its money, its CME future. On a world
 * map sized by each currency's trading, by session, hour by hour, as pairs, and biggest first. Read-only: nothing here
 * places an order. Labels and scales follow the period of the board on screen, never the switch. The page fills the
 * window and never scrolls (the world board kit it shares with the Global page).
 */
import { useState, type ReactNode } from 'react';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { HowToRead, Seg, StatusLine, type Note } from '../world_board/controls';
import { etDay, etTime } from '../world_board/format';
import {
  COLOR_BY, COLOR_BY_LABEL, FOREX_HOW_TO_READ, FOREX_OFF, FOREX_OLD_API, FOREX_PERIODS, FOREX_REPLAY_NOTE,
  FOREX_SUBTITLE, FOREX_TITLE, FUTURES_DEF, MIXED_DEF, PERIOD_LABEL, SIZE_DEF, SOURCES_DEF, STRENGTH_DEF,
} from './constants';
import { CurrencyList } from './CurrencyList';
import { FollowTheSun } from './FollowTheSun';
import { KpiStrip } from './KpiStrip';
import { MajorPairs } from './MajorPairs';
import { useForexPrefs } from './prefs';
import { statusNotes } from './status';
import type { ColorBy, ForexBoard } from './types';
import { useForexBoard } from './useForexBoard';
import { WorldMap } from './WorldMap';
import '../world_board/board.css';
import './forex.css';

function Head({ board, notes, children }: { board: ForexBoard | null; notes: Note[]; children?: ReactNode }) {
  const open = board ? board.sun.tracks.filter((t) => t.from <= board.generated_at && board.generated_at < t.to) : [];
  return (
    <div className={`gb-head${notes.length ? ' has-notes' : ''}`}>
      <h2>{FOREX_TITLE}</h2>
      <span className="gb-head__tag">{FOREX_SUBTITLE}</span>
      {board ? (
        <span className="gb-head__sub" data-testid="forex-head-sub">
          {etDay(board.generated_at)} · {etTime(board.generated_at)} ET · FX day since {etTime(board.fx_day.from)} ET
          {board.fx_day.open ? ` · ${open.length ? `${open.map((t) => t.name).join(' + ')} open` : 'between sessions'}` : ''}
        </span>
      ) : null}
      {board?.replay_desk ? <span className="gb-pill">{FOREX_REPLAY_NOTE}</span> : null}
      <StatusLine notes={notes} prefix="forex" />
      {children}
    </div>
  );
}

export function ForexPage() {
  const sample = useSampleRoute();
  const [prefs, setPrefs] = useForexPrefs(!sample);
  const { data: board, error, unavailable } = useForexBoard(prefs.period);
  const [hovered, setHovered] = useState<string | null>(null);

  const switches = (
    <div className="gb-switches">
      <span className="gb-muted">Color by</span>
      <Seg<ColorBy> value={prefs.colorBy} options={COLOR_BY} labels={COLOR_BY_LABEL}
        onPick={(colorBy) => setPrefs({ ...prefs, colorBy })} testId="forex-color-by" />
      <Seg value={prefs.period} options={FOREX_PERIODS} labels={PERIOD_LABEL}
        onPick={(period) => setPrefs({ ...prefs, period })} testId="forex-period" />
    </div>
  );

  if (unavailable || !board || !board.enabled) {
    const words = unavailable ? FOREX_OLD_API : board && !board.enabled ? FOREX_OFF : error ?? 'Reading the currencies …';
    return (
      <div className="gb-page fx-page" data-testid="forex-page">
        <Head board={null} notes={[]}>{switches}</Head>
        <p className="gb-wait" role="status">{words}</p>
      </div>
    );
  }

  const strengthOn = prefs.colorBy === 'strength';
  return (
    <div className="gb-page fx-page" data-testid="forex-page">
      <Head board={board} notes={statusNotes(board, prefs.period, error)}>{switches}</Head>
      <KpiStrip market={board.market} read={board.read} dollar={board.dollar} sessions={board.sessions} />
      <div className="gb-main">
        <div className="gb-left">
          <section className="gb-card gb-card--map">
            <div className="gb-card__head">
              <h3>World map</h3>
              <span className="gb-muted">
                bubble = the currency's trading a day (BIS) · colour = {strengthOn ? 'strength' : 'futures pressure'}
                {board.period === '1D' ? ' today' : ` · ${PERIOD_LABEL[board.period]}`} · dashed ring = its home session open
              </span>
              <span className="gb-legend">
                <i className="is-up" />{strengthOn ? 'Stronger' : 'Futures bought'}
                <i className="is-down" />{strengthOn ? 'Weaker' : 'Futures sold'}
                <i className="fx-none-key" />{strengthOn ? 'No IBKR price' : 'No futures'}
              </span>
            </div>
            <WorldMap currencies={board.currencies} colorBy={prefs.colorBy} period={board.period} now={board.generated_at}
              asOf={board.market.as_of} hovered={hovered} onHover={setHovered} />
          </section>
          <div className="gb-bottom fx-bottom">
            <section className="gb-card">
              <div className="gb-card__head">
                <h3>Follow the sun</h3>
                <span className="gb-muted">
                  {strengthOn ? 'strength' : 'futures pressure'} hour by hour · the FX day from {etTime(board.sun.from)} ET
                  · % = the desks' share of all forex
                </span>
              </div>
              <FollowTheSun sun={board.sun} colorBy={prefs.colorBy} />
            </section>
            <section className="gb-card">
              <div className="gb-card__head">
                <h3>Major pairs</h3>
                <span className="gb-muted">{board.period === '1D' ? "today's" : PERIOD_LABEL[board.period]} move, row against column</span>
              </div>
              <MajorPairs currencies={board.currencies} period={board.period} total={board.market.total_usd} />
            </section>
          </div>
        </div>
        <section className="gb-card gb-side">
          <div className="gb-card__head">
            <h3>By currency</h3>
            <span className="gb-muted">biggest first · {PERIOD_LABEL[board.period]}</span>
            <HowToRead label={FOREX_HOW_TO_READ} prefix="forex">
              <p>{SIZE_DEF}</p>
              <p>{STRENGTH_DEF}</p>
              <p>{FUTURES_DEF}</p>
              <p><span className="gb-flag">≠</span> {MIXED_DEF}</p>
              <p>{SOURCES_DEF}</p>
            </HowToRead>
          </div>
          <CurrencyList currencies={board.currencies} period={board.period} hovered={hovered} onHover={setHovered} />
        </section>
      </div>
    </div>
  );
}

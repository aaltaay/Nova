/**
 * What each colour on a Trader chart pane means (operator ask 2026-09-30: "where ever we need legend i need
 * you to add those cuz i get lost"). Pure: the rows the pane's Key chip lists, for what that pane draws --
 * the session tint behind the candles on every intraday pane; the levels each chart reads from its own
 * candles (5-minute, Full Day, and the 1-minute's nearest ones); the setup boxes and the plan's lines on
 * the 1-minute pane (the 10-second pane mirrors the plan's lines). Every colour is the one the drawing
 * uses, read from the same constants.
 */
import { CHART_SESSION_COLORS } from '../constants';
import { SHORT_SETUP_COLORS } from '../constantGroups/short_setups';
import type { PaneKind } from './chartShapes';
import { FLAT_TOP_COLORS, LEVEL_COLORS, SETUP_COLORS } from './constants';

/** How a row's swatch is drawn: a line (solid, long dash or dots), a filled band, a box, a ring (a flat top's
 * touch) or a triangle pointing up (its break). */
export type KeySwatch = 'line' | 'dash' | 'dots' | 'band' | 'box' | 'ring' | 'up';

export interface KeyRow {
  swatch: KeySwatch;
  color: string;
  /** The box's or band's fill, when it differs from `color`. */
  fill?: string;
  label: string;
  /** What it means, in a few plain words. */
  text: string;
}

export interface KeySection {
  title: string;
  rows: KeyRow[];
}

export interface KeyLayers {
  setups: boolean;
  levels: boolean;
}

const GREY = '#8e8e93';

function sessionRows(): KeySection {
  return {
    title: 'Background (time of day, ET)',
    rows: [
      { swatch: 'band', color: CHART_SESSION_COLORS.premarket, label: 'Premarket', text: '4:00–9:30 AM' },
      { swatch: 'band', color: CHART_SESSION_COLORS.rth, label: 'Regular hours', text: '9:30 AM–4:00 PM' },
      { swatch: 'band', color: CHART_SESSION_COLORS.afterhours, label: 'After hours', text: '4:00–8:00 PM' },
      { swatch: 'band', color: CHART_SESSION_COLORS.closed, label: 'Closed', text: '8:00 PM–4:00 AM' },
    ],
  };
}

const ZONE_ROWS: KeyRow[] = [
  { swatch: 'band', color: LEVEL_COLORS.support, label: 'Shaded band', text: 'how deep the zone goes; its line is the edge nearest the price' },
  { swatch: 'line', color: GREY, label: 'Thick line', text: 'a strong level (tested many times)' },
];

function fiveMinuteLevelRows(): KeySection {
  return {
    title: 'Levels from 5-minute candles (hover a label for why)',
    rows: [
      { swatch: 'line', color: LEVEL_COLORS.resistance, label: 'Resistance', text: 'above the price: tops 5-minute candles made, the high of day' },
      { swatch: 'line', color: LEVEL_COLORS.support, label: 'Support', text: 'below the price: bottoms, the premarket high, the open, the low' },
      { swatch: 'dash', color: LEVEL_COLORS.round, label: 'Round number', text: 'a round price the day tested ($X.00 / $X.50 up to $25, coarser above: $5 / $10 on a $225 stock)' },
      ...ZONE_ROWS,
    ],
  };
}

function dailyRows(): KeySection {
  return {
    title: 'Levels from past days (hover a label for why)',
    rows: [
      { swatch: 'dash', color: LEVEL_COLORS.daily, label: 'Old daily level', text: 'daily highs and lows, unfilled gaps, the 200-day' },
      { swatch: 'dots', color: LEVEL_COLORS.yesterday, label: "Yesterday's", text: "yesterday's high and low" },
      { swatch: 'line', color: LEVEL_COLORS.resistance, label: 'Resistance', text: 'several reasons above the price' },
      { swatch: 'line', color: LEVEL_COLORS.support, label: 'Support', text: 'several reasons below the price' },
      ...ZONE_ROWS,
    ],
  };
}

function minuteRows(): KeySection {
  return {
    title: 'Levels from 1-minute candles (hover a label for why)',
    rows: [
      { swatch: 'line', color: LEVEL_COLORS.resistance, label: 'Resistance', text: 'above the price: the nearest top 1-minute candles made, the high of day' },
      { swatch: 'line', color: LEVEL_COLORS.support, label: 'Support', text: 'below the price: the nearest bottom (or old top)' },
      { swatch: 'dash', color: LEVEL_COLORS.round, label: 'Round number', text: 'the nearest round price each side ($X.00 / $X.50 up to $25, coarser above)' },
      ...ZONE_ROWS,
    ],
  };
}

function setupRows(): KeySection {
  return {
    title: 'Setups',
    rows: [
      { swatch: 'box', color: SETUP_COLORS.formingStroke, fill: SETUP_COLORS.forming, label: 'Forming', text: 'the pattern is building' },
      { swatch: 'box', color: SETUP_COLORS.trigger, fill: SETUP_COLORS.leg, label: 'Armed / near', text: 'ready: waiting for the trigger price' },
      { swatch: 'box', color: SETUP_COLORS.target, fill: 'rgba(48, 209, 88, 0.12)', label: 'Triggered', text: 'price went through the trigger' },
      { swatch: 'box', color: SETUP_COLORS.fadedStroke, fill: SETUP_COLORS.faded, label: 'Ended (faint, dashed)', text: '✕ failed · ○ faded · ✓ triggered earlier' },
      { swatch: 'box', color: SHORT_SETUP_COLORS.stroke, fill: SHORT_SETUP_COLORS.fill, label: '▼ SHORT', text: 'a short setup (always labelled SHORT): its trigger under the pattern, its buy stop over it' },
    ],
  };
}

/** The flat top's own drawing (2026-10-06): the level, its touches, the base, the break and the hold -- on the
 * 5-minute pane the 5-minute flat top's, whose hold is a 1-minute candle (`five`). */
function flatTopRows(five = false): KeySection {
  const c = FLAT_TOP_COLORS;
  return {
    title: five ? '5-minute flat top (a strategy: it can trade)' : 'Flat top',
    rows: [
      { swatch: 'line', color: c.line, label: 'Flat top', text: 'the high of day the candles keep tapping (dashed while it forms)' },
      { swatch: 'ring', color: c.ringStroke, fill: c.ring, label: 'Touch', text: 'a candle whose high reached it (within 0.5% or a cent under it)' },
      { swatch: 'box', color: c.line, fill: c.fill, label: 'Base', text: 'the candles under it, from the first touch' },
      { swatch: 'up', color: c.go, label: 'Break', text: five ? 'the 5-minute candle a price over it printed in' : 'the candle that traded over it' },
      five
        ? { swatch: 'box', color: c.go, fill: c.holdFill, label: '1m hold', text: 'the 5-minute candle the entry printed in: the first 1-minute candle that held it and closed green' }
        : { swatch: 'box', color: c.go, fill: c.holdFill, label: 'Hold', text: 'the candle that held it and closed green: the entry' },
    ],
  };
}

function fiveMinuteRows(): KeySection {
  return {
    title: '5-minute setups (labels start "5m")',
    rows: [
      { swatch: 'box', color: SETUP_COLORS.formingStroke, fill: SETUP_COLORS.forming, label: 'Forming', text: 'a pattern building on 5-minute candles' },
      { swatch: 'box', color: SETUP_COLORS.trigger, fill: SETUP_COLORS.leg, label: 'Armed / near', text: 'waiting for its trigger' },
      { swatch: 'box', color: SETUP_COLORS.fadedStroke, fill: SETUP_COLORS.faded, label: 'Ended (faint)', text: '✕ failed · ○ faded · ✓ triggered, and what price did next' },
      { swatch: 'dash', color: SETUP_COLORS.trigger, label: '5m trigger', text: 'with its stop (red) and target (green), dashed' },
      { swatch: 'line', color: GREY, label: 'Scored only', text: 'the first pullback and the bull flag: Nova scores them in silence, they never propose or trade' },
    ],
  };
}

function fiveOnMinuteRows(): KeySection {
  const c = FLAT_TOP_COLORS;
  return {
    title: 'From the 5-minute chart',
    rows: [
      { swatch: 'dash', color: SETUP_COLORS.trigger, label: '5m trigger', text: 'a 5-minute setup armed or near its trigger (its chip is in the legend)' },
      { swatch: 'line', color: c.line, label: '5m flat top', text: 'once it arms: its level from the first touch, the break, and the 1-minute candle that holds it (the entry)' },
    ],
  };
}

function planRows(full: boolean): KeySection {
  const rows: KeyRow[] = [
    { swatch: 'line', color: SETUP_COLORS.trigger, label: 'Entry', text: 'where the plan buys (a short plan: where it shorts)' },
    { swatch: 'line', color: SETUP_COLORS.stop, label: 'Stop', text: 'where the plan gets out at a loss' },
    { swatch: 'line', color: SETUP_COLORS.target, label: 'Target', text: 'where the plan takes profit' },
  ];
  if (full) {
    rows.push(
      { swatch: 'band', color: SETUP_COLORS.risk, label: 'Red zone', text: 'the risk: from the entry to the stop (over the entry on a short)' },
      { swatch: 'band', color: SETUP_COLORS.reward, label: 'Green zone', text: 'the reward: from the entry to the target (under it on a short)' },
    );
  }
  rows.push({ swatch: 'dash', color: GREY, label: 'Dashed vs solid', text: 'dashed: only a plan · solid: an order is working' });
  return { title: 'The plan', rows };
}

/** The Key's sections for one pane; empty for a pane Nova draws nothing on. */
export function chartKey(kind: PaneKind, layers: KeyLayers): KeySection[] {
  if (kind === 'none') return [];
  const out: KeySection[] = [];
  if (kind === 'full') {
    if (layers.setups) out.push(setupRows(), flatTopRows());
    out.push(planRows(true));
    if (layers.levels) out.push(minuteRows());
    if (layers.setups) out.push(fiveOnMinuteRows());
  } else if (kind === 'thin') {
    out.push(planRows(false));
  } else {
    if (kind === 'map' && layers.setups) out.push(fiveMinuteRows(), flatTopRows(true));
    if (layers.levels) out.push(kind === 'daily' ? dailyRows() : fiveMinuteLevelRows());
  }
  if (kind !== 'daily') out.push(sessionRows());
  return out;
}

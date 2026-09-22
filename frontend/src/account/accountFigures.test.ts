import { describe, expect, it } from 'vitest';
import { figuresFromPractice, figuresFromSummary } from '../components/headerAccountFigures';
import {
  accountDetailRows,
  componentRings,
  rangeNetPnl,
  sourceCards,
  sourceLabel,
  symbolPnlRows,
  todayDailyRow,
  todayPracticeDate,
} from './accountFigures';
import { PAPER_ACCOUNT_TODAY, paperHistoryFixture } from './accountFixtures';

describe('accountDetailRows', () => {
  it('reads realized / commissions / fees from today\'s ledger row and reconciles to Day\'s P&L', () => {
    const history = paperHistoryFixture();
    const today = todayPracticeDate();
    const rows = accountDetailRows(figuresFromPractice(PAPER_ACCOUNT_TODAY), todayDailyRow(history, today), true);
    expect(rows.realizedToday).toBe(97.5);
    expect(rows.openPnl).toBe(55);
    expect(rows.commissionsToday).toBe(10);
    expect(rows.feesToday).toBe(0.4);
    expect(rows.dayPnl).toBe(142.1);
    expect(rows.reconcile).toBe('ok');
    expect(rows.residual).toBeCloseTo(0, 6);
    expect(rows.excessLiquidity).toBeNull();
  });

  it('states a residual when a carried-in position moves Day\'s P&L off the rows', () => {
    const history = paperHistoryFixture();
    const account = { ...PAPER_ACCOUNT_TODAY, day_pnl: 100 };
    const rows = accountDetailRows(figuresFromPractice(account), todayDailyRow(history, todayPracticeDate()), true);
    expect(rows.reconcile).toBe('residual');
    expect(rows.residual).toBeCloseTo(42.1, 6);
  });

  it('is an honest zero with a loaded history and no row today, unknown before the history answers', () => {
    const loaded = accountDetailRows(figuresFromPractice(PAPER_ACCOUNT_TODAY), null, true);
    expect(loaded.realizedToday).toBe(0);
    expect(loaded.commissionsToday).toBe(0);
    const pending = accountDetailRows(figuresFromPractice(PAPER_ACCOUNT_TODAY), null, false);
    expect(pending.realizedToday).toBeNull();
    expect(pending.reconcile).toBe('unknown');
  });

  it('on Live takes IBKR RealizedPnL and leaves the fee split null', () => {
    const rows = accountDetailRows(
      figuresFromSummary({ connected: true, mode: 'live', RealizedPnL: 12, UnrealizedPnL: -3, NetLiquidation: 5000, ExcessLiquidity: 4000 }),
      null,
      false,
    );
    expect(rows.realizedToday).toBe(12);
    expect(rows.commissionsToday).toBeNull();
    expect(rows.excessLiquidity).toBe(4000);
    expect(rows.reconcile).toBe('unknown');
  });

  it('never picks an archived row for today', () => {
    const history = paperHistoryFixture();
    const today = todayPracticeDate();
    history.daily = [{ date: today, realized: 1, commissions: 0, fees: 0, fills: 1, archived: true }];
    expect(todayDailyRow(history, today)).toBeNull();
  });
});

describe('symbolPnlRows', () => {
  it('attributes realized and costs per symbol, open from positions, and totals', () => {
    const history = paperHistoryFixture();
    const { rows, total } = symbolPnlRows(history.fills, [{ symbol: 'GRML', unrealized: 55 }]);
    const grml = rows.find((r) => r.symbol === 'GRML')!;
    const qnme = rows.find((r) => r.symbol === 'QNME')!;
    expect(grml.realized).toBe(125);
    expect(grml.costs).toBeCloseTo(7.7, 6);
    expect(grml.open).toBe(55);
    expect(grml.net).toBeCloseTo(125 + 55 - 7.7, 6);
    expect(qnme.realized).toBe(-27.5);
    expect(qnme.open).toBeNull();
    expect(total.realized).toBe(97.5);
    expect(total.costs).toBeCloseTo(10.4, 6);
    expect(total.net).toBeCloseTo(142.1, 6);
  });
});

describe('sourceCards', () => {
  it('always shows Manual, Bot and Auto Paper -- a source with no fills is stated, not zero', () => {
    const cards = sourceCards(paperHistoryFixture().by_source);
    expect(cards.map((c) => c.kind)).toEqual(['manual', 'bot', 'auto_paper']);
    const manual = cards[0];
    const bot = cards[1];
    const auto = cards[2];
    expect(manual.net).toBeCloseTo(125 - 7.5 - 0.2, 6);
    expect(bot.net).toBeCloseTo(-27.5 - 2.5 - 0.2, 6);
    expect(bot.label).toBe('Bot · momo-1');
    expect(auto.net).toBeNull();
    expect(auto.share).toBe(0);
    expect(manual.share + bot.share).toBeCloseTo(1, 6);
  });

  it('labels sources from the stamp', () => {
    expect(sourceLabel('manual', null)).toBe('Manual');
    expect(sourceLabel('bot', 'x')).toBe('Bot · x');
    expect(sourceLabel('auto_paper', null)).toBe('Auto Paper');
    expect(sourceLabel('flatten', null)).toBe('flatten');
  });
});

describe('componentRings', () => {
  it('shares are of the absolute total; the bot ring is share of gross realized', () => {
    const history = paperHistoryFixture();
    const rings = componentRings(history.components, history.fills);
    const total = 97.5 + 55 + 10 + 0.4;
    expect(rings.find((r) => r.id === 'realized')!.share).toBeCloseTo(97.5 / total, 6);
    expect(rings.find((r) => r.id === 'fees')!.share).toBeCloseTo(0.4 / total, 6);
    expect(rings.find((r) => r.id === 'commissions')!.value).toBe(-10);
    expect(rings.find((r) => r.id === 'bot')!.share).toBeCloseTo(27.5 / (125 + 27.5), 6);
    expect(rangeNetPnl(history.components)).toBeCloseTo(142.1, 6);
  });
});

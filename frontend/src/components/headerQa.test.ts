/**
 * Header findings from the QA sweep of 2026-09-22: V15 (cards), C24 (Sim
 * chip), C25 (Paper tooltip), C58 (status 500), C61 (day start), C68
 * (practice notices), V34 (roster wording, checklist hint).
 */
import { describe, expect, it } from 'vitest';
import {
  CLUSTER_MENU_CLOSED,
  clusterMenuOnClick,
  clusterMenuOnHover,
} from './globalBarMenuToggle';
import { connectionChipView, humanRosterText, type ConnectionChipInput } from './globalBarConnectionModel';
import { formatDayStartEt } from './headerAccountFigures';
import { deskGatewayView } from './headerConnectionStatusModel';

describe('header cards: hover opens, click pins, click again closes (V15)', () => {
  it('a click after the hover that opened the card keeps it open', () => {
    const hovered = clusterMenuOnHover(CLUSTER_MENU_CLOSED, 'day');
    expect(hovered).toEqual({ open: 'day', pinned: false });
    const clicked = clusterMenuOnClick(hovered, 'day');
    expect(clicked).toEqual({ open: 'day', pinned: true });
    expect(clusterMenuOnClick(clicked, 'day')).toEqual(CLUSTER_MENU_CLOSED);
  });

  it('the keyboard (a click with no hover) toggles as before', () => {
    const opened = clusterMenuOnClick(CLUSTER_MENU_CLOSED, 'tav');
    expect(opened.open).toBe('tav');
    expect(clusterMenuOnClick(opened, 'tav')).toEqual(CLUSTER_MENU_CLOSED);
  });

  it('pointing at another trigger switches cards; pointing back keeps a pin', () => {
    const pinned = clusterMenuOnClick(CLUSTER_MENU_CLOSED, 'working');
    expect(clusterMenuOnHover(pinned, 'working')).toBe(pinned);
    expect(clusterMenuOnHover(pinned, 'pill')).toEqual({ open: 'pill', pinned: false });
  });
});

describe('Day P&L tooltip names the day start in ET (C61)', () => {
  it('formats the ledger ISO, never prints it raw', () => {
    expect(formatDayStartEt('2026-09-21T04:00:00-04:00')).toBe('Mon, Sep 21, 04:00 ET');
    expect(formatDayStartEt(null)).toBeNull();
    expect(formatDayStartEt('not a date')).toBeNull();
  });
});

function chip(overrides: Partial<ConnectionChipInput>): ReturnType<typeof connectionChipView> {
  return connectionChipView({
    sampleDataActive: false,
    apiOk: true,
    apiTitle: 'api',
    connected: true,
    statusStale: false,
    staleForSec: null,
    delayed: false,
    gatewayTitle: 'gateway',
    pricesStale: false,
    secondsAgo: null,
    historyDate: null,
    isIbkr: true,
    activeFeed: 'sip',
    feedFellBack: false,
    ...overrides,
  });
}

describe('connection chip', () => {
  it('on Sim with the Gateway down is amber "IBKR offline", never green "IBKR live" (C24)', () => {
    const view = chip({ venue: 'sim', connected: false });
    expect(view.label).toBe('IBKR offline');
    expect(view.tone).toBe('warn');
    expect(view.title).toMatch(/Sim replays recorded sessions without IB Gateway/);
    expect(chip({ venue: 'live', connected: false }).tone).toBe('bad');
  });

  it('says it is checking while the first status poll is pending, never "IBKR offline" (QA D10)', () => {
    const view = chip({ connected: false, statusPending: true });
    expect(view.label).toBe('Checking IBKR');
    expect(view.state).toBe('checking');
    expect(view.title).toMatch(/has not answered yet/);
    // Once the status answers, a real outage is still an outage.
    expect(chip({ connected: false, statusPending: false }).label).toBe('IBKR offline');
  });

  it('puts the roster error in words (V34)', () => {
    expect(humanRosterText('ibkr: TimeoutError: TimeoutError()')).toBe('IBKR scanner request timed out');
    expect(humanRosterText('ibkr: ConnectionRefusedError: [Errno 111]')).toBe('IBKR scanner connection failed');
    expect(humanRosterText('last-good')).toBe('last-good');
    expect(chip({ honestyText: 'ibkr: TimeoutError: TimeoutError()' }).title).toContain('Roster: IBKR scanner request timed out');
  });
});

const GATEWAY = {
  gatewayMode: 'live' as const,
  accountKind: 'paper',
  connected: true,
  delayed: false,
  statusStale: false,
  launchOk: null,
  launchHint: null,
};

describe('gateway tooltip', () => {
  it('on Paper names the practice venue and the live login separately (C25)', () => {
    const { title } = deskGatewayView({ ...GATEWAY, ibkrMode: 'paper', venue: 'paper' });
    expect(title).toMatch(/Nova's practice account on the live feed/);
    expect(title).toMatch(/IB Gateway on the live port/);
    expect(title).not.toMatch(/IBKR account class: PAPER/);
  });

  it('a failed status request says so instead of blaming the Gateway (C58)', () => {
    const { title } = deskGatewayView({
      ...GATEWAY, ibkrMode: 'live', venue: 'live', connected: false, statusStale: true, statusError: 'HTTP 500',
    });
    expect(title).toMatch(/status request failed \(HTTP 500\)/);
    expect(title).not.toMatch(/Log into IB Gateway|not connected/i);
  });

  it('keeps the IBKR completed-orders notice off the practice venues (C68)', () => {
    const since = 1_789_808_049;
    const live = deskGatewayView({ ...GATEWAY, ibkrMode: 'live', venue: 'live', completedOrdersUnansweredSince: since });
    const paper = deskGatewayView({ ...GATEWAY, ibkrMode: 'paper', venue: 'paper', completedOrdersUnansweredSince: since });
    expect(live.title).toMatch(/Completed orders not answering since/);
    expect(paper.title).not.toMatch(/Completed orders not answering since/);
  });

  it('points at this chip, not a Desk chip that no longer exists (V34)', () => {
    expect(deskGatewayView({ ...GATEWAY, ibkrMode: 'live' }).title).not.toMatch(/Click Desk/);
  });
});

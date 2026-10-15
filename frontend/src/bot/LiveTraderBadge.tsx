/**
 * "BOT 48 sh" beside the ticker of a host's open row on Bots > LiveTrader Bots while the host's bot holds a copy of it
 * (ADR 055; approved render, 2026-10-15): its shares, its own entry, the host's average and its P/L on hover. Nothing
 * when the bot holds none of it.
 */
import { ltBadge, ltBotOf } from '../constantGroups/live_trader';
import type { FollowedTrade } from '../followed_traders';
import { tipProps } from '../ux';
import { copies, positionTip } from './liveTraderFormat';
import { useLiveTraders } from './liveTraderStore';
import './liveTraderStrip.css';

export function LiveTraderBadge({ trade }: { trade: FollowedTrade }) {
  const { view } = useLiveTraders();
  const host = view?.enabled ? view.hosts.find(h => h.name === trade.trader) ?? null : null;
  const copy = host?.positions.find(p => copies(p, trade)) ?? null;
  if (!host || !copy) return null;
  return (
    <span className="lt-badge" data-testid={`lt-badge-${trade.id}`} {...tipProps(positionTip(copy), ltBotOf(host.name))}>
      {ltBadge(copy.qty)}
    </span>
  );
}

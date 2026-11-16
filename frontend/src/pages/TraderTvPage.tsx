/**
 * TraderTV, on the rail under Congress (ADR 072; approved mockup retire-bots v1): the TraderTV hosts' page --
 * who is on air, what each holds and closed, priced with Nova's IBKR data, the stream and the Activity -- with
 * the desk's Positions / Orders · today dock under it, as LiveTrader Bots had it. ADR 072 retired the Live
 * Trader bot, so nothing here trades: no Bot key, no host bot, no BOT chip on a copied row. The sample desk
 * has no hosts' feed, and says so.
 */
import { FollowedTradersPage } from '../followed_traders';
import { ScannerDesk } from '../scanner';
import { SAMPLE_TRADERTV_ABSENT } from '../sample_data/sampleCopy';
import { useSampleRoute } from '../sample_data/useSampleRoute';

export function TraderTvPage({ onOpenTrader }: { onOpenTrader?: (symbol: string) => void }) {
  const sample = useSampleRoute();
  if (sample) {
    return (
      <div className="nova-shell nova-shell--scanner">
        <div className="main-col main-col--scanner-stack">
          <p className="na-muted" role="status" data-testid="tradertv-sample-absent" style={{ padding: 16 }}>
            {SAMPLE_TRADERTV_ABSENT}
          </p>
        </div>
      </div>
    );
  }
  return (
    <ScannerDesk host="bots" onOpenTrading={onOpenTrader}>
      <FollowedTradersPage onOpenTrader={onOpenTrader} />
    </ScannerDesk>
  );
}

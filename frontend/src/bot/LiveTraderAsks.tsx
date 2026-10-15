/**
 * The Live Trader bot's asks as toasts in every desk window (ADR 055; operator, 2026-10-14: "It's probably better to
 * have this also as a toast notification"): with a host's Entry on You and Exit on Bot, each step the host takes is
 * an ask -- "SHAWN shorted XYZ at 43.12: short 11 at 43.10, buy stop 45.26?" -- with Skip and Approve and the seconds
 * it has left. It rides with the bot's notices (`BotNotices`), polls only on a desk with a TraderTV feed, and the
 * backend checks every rule again before an approved step goes out.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { LT_ANSWERED_WHY, LT_APPROVE, LT_BUSY_WHY, LT_SKIP } from '../constantGroups/live_trader';
import { useFollowedTradersEnabled } from '../followed_traders';
import { whyProps } from '../ux';
import { prose } from './botsPageFormat';
import { answerLiveTraderAsk } from './liveTraderApi';
import { secondsLeft } from './liveTraderFormat';
import { asksPoll, useLiveTraderAsks } from './liveTraderStore';
import type { LtAsk } from './liveTraderTypes';

function AskToast({ ask, now }: { ask: LtAsk; now: number }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answered = ask.answered != null || ask.approved;
  const locked = busy || answered;
  const why = busy ? LT_BUSY_WHY : LT_ANSWERED_WHY;

  async function answer(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      await answerLiveTraderAsk(ask.host ?? '', ask.id, approve);
      void asksPoll.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bot-notice bot-notice--warn lt-ask-toast" role="alert" data-testid={`lt-ask-toast-${ask.id}`}>
      <div className="bot-notice__text">
        <strong className="bot-notice__title">Live Trader · {ask.host}</strong>
        <span className="bot-notice__body">{prose(ask.text)}</span>
        <span className="bot-notice__body">
          {answered ? 'approved — checking every rule again before it goes out' : `${secondsLeft(ask.expires_ts, now)} s left`}
        </span>
        {error ? <span className="bot-notice__body lt-ask-toast__error">{error}</span> : null}
        <span className="lt-ask-toast__acts">
          <button type="button" className="bots-btn" disabled={locked} {...whyProps(locked, why)}
            data-testid={`lt-ask-toast-skip-${ask.id}`} onClick={() => void answer(false)}>{LT_SKIP}</button>
          <button type="button" className="bots-btn bots-btn--primary" disabled={locked} {...whyProps(locked, why)}
            data-testid={`lt-ask-toast-approve-${ask.id}`} onClick={() => void answer(true)}>{LT_APPROVE}</button>
        </span>
      </div>
    </div>
  );
}

/** The asks' toasts, for the bot's notices to stack with its own (one stack, bottom left). */
export function useLiveTraderAskToasts(): ReactNode[] {
  const enabled = useFollowedTradersEnabled();
  const { view } = useLiveTraderAsks(enabled);
  const asks = enabled ? view?.asks ?? [] : [];
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!asks.length) return undefined;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, [asks.length]);
  return asks.map(ask => <AskToast key={ask.id} ask={ask} now={now} />);
}

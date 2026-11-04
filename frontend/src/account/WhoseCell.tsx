/**
 * Whose a row is (ADR 069): the chip -- You, or the bot's name -- and, on a bots' position row on Paper, the
 * Close that sells the bots' shares in that stock (`POST /api/owners/close-bots`; your shares stay). Close asks
 * once more before it sends ("Sell 12?", for a few seconds), and a refused Close says why on the row; nothing is
 * ever silent.
 */
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import {
  OWNER_CLOSE_BOTS,
  OWNER_CLOSE_BOTS_ARM_MS,
  OWNER_CLOSE_BOTS_OFF_PAPER,
  OWNER_CLOSE_BOTS_SENDING,
  ownerCloseBotsConfirm,
  ownerCloseBotsTitle,
} from '../constantGroups/owners';
import { closeBots } from './ownersApi';
import { whoName } from './ownerView';

interface ChipProps {
  owner: 'you' | 'bots' | null | undefined;
  bot: string | null | undefined;
}

export function WhoseChip({ owner, bot }: ChipProps) {
  const tone = owner === 'you' ? 'is-you' : bot === 'claude' ? 'is-claude' : 'is-bots';
  return <span className={`acct-who ${tone}`} data-testid="account-whose">{whoName(owner, bot)}</span>;
}

export function CloseBotsButton({ symbol, qty, paper }: { symbol: string; qty: number; paper: boolean }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!armed) return undefined;
    const timer = window.setTimeout(() => setArmed(false), OWNER_CLOSE_BOTS_ARM_MS);
    return () => window.clearTimeout(timer);
  }, [armed]);
  const why = paper ? null : OWNER_CLOSE_BOTS_OFF_PAPER;
  const title = why ?? ownerCloseBotsTitle(symbol, qty);
  const press = async () => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setArmed(false);
    setBusy(true);
    setError(null);
    try {
      await closeBots(symbol);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className={`acct-close-bots${armed ? ' is-armed' : ''}`} disabled={busy || !paper}
        aria-disabled={busy || !paper} data-why={why ?? undefined} title={title}
        aria-label={armed ? ownerCloseBotsConfirm(qty) : `${OWNER_CLOSE_BOTS}: ${title}`}
        data-testid={`account-close-bots-${symbol}`} onClick={press}>
        {busy ? OWNER_CLOSE_BOTS_SENDING : armed ? ownerCloseBotsConfirm(qty) : <X size={11} strokeWidth={2.2} aria-hidden />}
      </button>
      {error && <span className="acct-neg" role="alert" data-testid="account-close-bots-error"> {error}</span>}
    </>
  );
}

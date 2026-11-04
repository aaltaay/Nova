/**
 * Whose a row is (ADR 069): the chip -- You, or the bot's name -- and, on a bots' position row on Paper, the
 * Close that sells the bots' shares in that stock (`POST /api/owners/close-bots`; your shares stay). Close asks
 * once more before it sends ("Sell all 12?", "Buy back all 19?", for a few seconds), and a refused Close says why
 * on the row; nothing is ever silent. The Account page draws the small chip and the icon; every other positions
 * list the pill and the word (decision 9).
 */
import { useEffect, useState, type MouseEvent } from 'react';
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
import './whose.css';

interface ChipProps {
  owner: 'you' | 'bots' | null | undefined;
  bot: string | null | undefined;
  /** The desk's lists draw a pill; the Account page's tight rows the small chip. */
  pill?: boolean;
}

export function WhoseChip({ owner, bot, pill = false }: ChipProps) {
  // Auto-entry's shares sit on your row, yours to sell: the chip still names who bought them.
  const who = bot ? 'bots' : owner;
  const tone = who === 'you' ? 'is-you' : bot === 'claude' ? 'is-claude' : 'is-bots';
  return <span className={`acct-who ${tone}${pill ? ' is-pill' : ''}`} data-testid="account-whose">{whoName(who, bot)}</span>;
}

interface CloseProps {
  symbol: string;
  /** Every bot's shares in the stock, signed: what the Close sells or buys back. */
  qty: number;
  paper: boolean;
  /** The Account page's X, or the word every other positions list shows. */
  look?: 'icon' | 'word';
}

export function CloseBotsButton({ symbol, qty, paper, look = 'icon' }: CloseProps) {
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
  const press = async (e: MouseEvent) => {
    e.stopPropagation();  // a table row's click opens the Trader
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
  const rest = look === 'word' ? OWNER_CLOSE_BOTS : <X size={11} strokeWidth={2.2} aria-hidden />;
  return (
    <>
      <button type="button" className={`acct-close-bots${look === 'word' ? ' is-word' : ''}${armed ? ' is-armed' : ''}`}
        disabled={busy || !paper}
        aria-disabled={busy || !paper} data-why={why ?? undefined} title={title}
        aria-label={armed ? ownerCloseBotsConfirm(qty) : `${OWNER_CLOSE_BOTS}: ${title}`}
        data-testid={`account-close-bots-${symbol}`} onClick={press}>
        {busy ? OWNER_CLOSE_BOTS_SENDING : armed ? ownerCloseBotsConfirm(qty) : rest}
      </button>
      {error && <span className="acct-close-bots__why" role="alert" data-testid="account-close-bots-error"> {error}</span>}
    </>
  );
}

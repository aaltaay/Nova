/** The symbol name. A click opens that day in Nova through the same path as the MCP tool. */

import { useState } from 'react';
import { openInNova } from './openInNova';

export function ReviewSymbolButton({
  symbol,
  date,
  asOf,
  showNote = true,
  onNote,
}: {
  symbol: string;
  date: string;
  asOf: string;
  showNote?: boolean;
  onNote?: (message: string) => void;
}) {
  const [note, setNote] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onClick() {
    if (pending) return;
    setPending(true);
    try {
      const result = await openInNova({ symbol, date, asOf });
      setNote(result.message);
      onNote?.(result.message);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Open failed';
      setNote(message);
      onNote?.(message);
    } finally {
      setPending(false);
    }
  }

  return (
    <span className="review-open">
      <button
        type="button"
        className="review-open__symbol review-cell__link"
        data-testid="review-open-symbol"
        aria-label={`Open ${symbol} in Nova`}
        disabled={pending}
        onClick={() => { void onClick(); }}
      >
        {symbol}
      </button>
      {showNote && note ? <span className="review-open__note" role="status">{note}</span> : null}
    </span>
  );
}

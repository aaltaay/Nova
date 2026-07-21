/** Quote header: symbol, price, blocklist toggle, description, last-updated. */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL, QUOTE_CARD_TITLE } from '../constants';
import type { TickerDetail } from '../types/ticker';
import { fmtPct, fmtTimestamp } from '../utils/quoteFormat';
import { confirmApp } from '../ux';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from './quoteMetrics';

const API_URL = `${API_BASE_URL}/api`;

interface Props {
  detail: TickerDetail;
  /** When true, omit the quote title/price block — parent page already shows it. */
  hideHeader?: boolean;
  /** Show bottom timestamp (stack layout). Default true when lastUpdated exists. */
  showTimestamp?: boolean;
}

export function QuoteHeaderPanel({
  detail,
  hideHeader = false,
  showTimestamp = true,
}: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/hod-momo/blocklist`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (!cancelled) setBlocked(!!data?.symbols?.includes(detail.symbol));
      })
      .catch((err) => {
        console.error('[Nova] HOD blocklist fetch failed', err);
      });
    return () => {
      cancelled = true;
    };
  }, [detail.symbol]);

  function onToggleBlock() {
    if (blocked) {
      novaFetch(`${API_URL}/hod-momo/blocklist/${detail.symbol}`, { method: 'DELETE' })
        .then(r => {
          if (r.ok) setBlocked(false);
        })
        .catch((err) => {
          console.error('[Nova] HOD blocklist unblock failed', err);
        });
      return;
    }
    void confirmApp({
      title: `Block ${detail.symbol}?`,
      message:
        'This removes it from every scanner (Gappers, Movers, After-Hours, News Catalysts) ' +
        'and HOD Momo alerts until you unblock it.',
      confirmLabel: 'Block',
      tone: 'danger',
    }).then(ok => {
      if (!ok) return;
      novaFetch(`${API_URL}/hod-momo/blocklist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: detail.symbol }),
      })
        .then(r => {
          if (r.ok) setBlocked(true);
        })
        .catch(err => {
          console.error('[Nova] HOD blocklist block failed', err);
        });
    });
  }

  return (
    <div className="nova-module nova-module--quote-header" data-module="quote-header">
      {!hideHeader && (
        <>
          <div className="cq-section-title cq-card-title">{QUOTE_CARD_TITLE}</div>
          <div className="cq-header">
            <div className="cq-symbol-row">
              <span className="cq-symbol">{detail.symbol}</span>
              {(m.mainChangeAbs != null || m.extChangeAbs != null) && (
                <span className="cq-trend">{m.isPositive ? '▲' : '▼'}</span>
              )}
              <button
                className={`cq-block-btn${blocked ? ' cq-block-btn--blocked' : ''}`}
                onClick={onToggleBlock}
                title={blocked ? 'Remove from HOD Momo blocklist' : 'Add to HOD Momo blocklist'}
              >
                {blocked ? 'Unblock' : 'Block'}
              </button>
            </div>
            {m.mainPrice != null && (
              <div className="cq-price-row">
                <span className="cq-price">{m.mainPrice.toFixed(2)}</span>
                {m.mainChangeAbs != null && (
                  <span
                    className={`cq-change ${(m.mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}
                  >
                    {m.mainChangeAbs >= 0 ? '+' : ''}
                    {m.mainChangeAbs.toFixed(2)} ({fmtPct(m.mainChangePct)})
                  </span>
                )}
              </div>
            )}
            {m.isExtendedHours && m.extPrice != null && (
              <div className="cq-ext-row">
                <span className="cq-ext-label">{m.extLabel}:</span>
                <span className="cq-ext-price">{m.extPrice.toFixed(2)}</span>
                {m.extChangeAbs != null && (
                  <span className={`cq-ext-change ${m.extIsPositive ? 'positive' : 'negative'}`}>
                    {m.extChangeAbs >= 0 ? '+' : ''}
                    {m.extChangeAbs.toFixed(2)} ({fmtPct(m.extChangePct)})
                  </span>
                )}
              </div>
            )}
          </div>
        </>
      )}
      {hideHeader && (
        <div className="cq-symbol-row cq-detail-actions">
          <button
            className={`cq-block-btn${blocked ? ' cq-block-btn--blocked' : ''}`}
            onClick={onToggleBlock}
            title={blocked ? 'Remove from HOD Momo blocklist' : 'Add to HOD Momo blocklist'}
          >
            {blocked ? 'Unblock' : 'Block'}
          </button>
        </div>
      )}
      {m.descParts.length > 0 && (
        <div className="cq-description">{m.descParts.join(' | ')}</div>
      )}
      {showTimestamp && m.lastUpdated && (
        <div className="cq-timestamp">Last updated on {fmtTimestamp(m.lastUpdated)}</div>
      )}
    </div>
  );
}

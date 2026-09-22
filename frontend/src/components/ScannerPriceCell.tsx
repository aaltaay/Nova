/** Price cell with up/down flash and optional stale tint. */
import { SCANNER_PRICE_FLASH_MS } from '../constants';
import {
  SCANNER_CELL_ABSENT,
  SCANNER_PRICE_CLOSE_TAG,
  SCANNER_PRICE_CLOSE_TITLE,
} from '../constantGroups/scanner_board';
import { fmtPrice } from '../utils/quoteFormat';
import { useEffect, useState } from 'react';

interface Props {
  symbol: string;
  price: number | null | undefined;
  flash?: 'up' | 'down';
  stale?: boolean;
  /** The price is IBKR's prior close (quote_quality close_fallback) -- QA C50. */
  closeFallback?: boolean;
}

export function ScannerPriceCell({ symbol, price, flash, stale, closeFallback = false }: Props) {
  const [flashClass, setFlashClass] = useState('');

  useEffect(() => {
    if (!flash) return;
    setFlashClass(flash === 'up' ? 'price-flash-up' : 'price-flash-down');
    const id = setTimeout(() => setFlashClass(''), SCANNER_PRICE_FLASH_MS);
    return () => clearTimeout(id);
  }, [flash, symbol, price]);

  const classes = [
    'scanner-price-cell',
    flashClass,
    stale ? 'scanner-price-cell--stale' : '',
    closeFallback ? 'scanner-price--close-fallback' : '',
  ].filter(Boolean).join(' ');

  if (price == null) return <span className={`${classes} na-muted`}>{SCANNER_CELL_ABSENT}</span>;
  if (closeFallback) {
    return (
      <span className={classes} title={SCANNER_PRICE_CLOSE_TITLE} data-quote-quality="close_fallback">
        {fmtPrice(price)}
        <span className="scanner-price__close-tag">{SCANNER_PRICE_CLOSE_TAG}</span>
      </span>
    );
  }
  return <span className={classes}>{fmtPrice(price)}</span>;
}

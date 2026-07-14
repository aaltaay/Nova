/** Price cell with up/down flash and optional stale tint. */
import { SCANNER_PRICE_FLASH_MS } from '../constants';
import { fmtPrice } from '../utils/quoteFormat';
import { useEffect, useState } from 'react';

interface Props {
  symbol: string;
  price: number | null | undefined;
  flash?: 'up' | 'down';
  stale?: boolean;
}

export function ScannerPriceCell({ symbol, price, flash, stale }: Props) {
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
  ].filter(Boolean).join(' ');

  return <span className={classes}>{fmtPrice(price)}</span>;
}

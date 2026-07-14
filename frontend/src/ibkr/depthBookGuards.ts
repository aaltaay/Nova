import { L2_MM_OVERNIGHT } from '../constants';
import type { DepthBook, DepthLevel } from './types';

/** True when both sides of the book have zero rows. */
export function bookIsEmpty(book: DepthBook): boolean {
  return book.bids.length === 0 && book.asks.length === 0;
}

function levelMm(level: DepthLevel): string {
  return (level.mm || '').trim().toUpperCase();
}

/**
 * After the regular session, IBKR often only shows OVERNIGHT session quotes
 * (1–2 rows). That is venue data, not a Nova depth bug — surface a hint so it
 * is not mistaken for a broken ladder / wrong app.
 */
export function isOvernightOnlyBook(book: DepthBook): boolean {
  const levels = [...book.bids, ...book.asks];
  if (levels.length === 0) return false;
  return levels.every(level => levelMm(level) === L2_MM_OVERNIGHT);
}

/**
 * IBKR DOM refreshes can emit a transient empty book between real updates.
 * Keep the prior montage instead of blanking to "Connecting…" / empty rows.
 * L1-fallback empties are allowed through (they signal entitlement fallback).
 */
export function shouldKeepPriorBook(
  incoming: DepthBook,
  prior: DepthBook | null,
): boolean {
  if (
    prior?.symbol != null &&
    incoming.symbol != null &&
    prior.symbol !== incoming.symbol
  ) {
    return false;
  }
  return (
    bookIsEmpty(incoming) &&
    !incoming.l1_fallback &&
    prior != null &&
    !bookIsEmpty(prior)
  );
}

/**
 * Thin after-hours / overnight books (often 1–2 rows, MM=OVERNIGHT) are still
 * real depth and must render — never treat them as "no book yet".
 */
export function isRenderableBook(book: DepthBook | null): boolean {
  if (book == null) return false;
  if (book.l1_fallback) return true;
  return !bookIsEmpty(book);
}

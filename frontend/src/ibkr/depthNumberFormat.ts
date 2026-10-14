/** Numeric text on the live depth ladder, book-watch marks and LULD bands (#797). */
// Reuse the locale formatters instead of rebuilding price options on every active book/annotation.
const depthPrice = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const bandPrice = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const groupedNumber = new Intl.NumberFormat('en-US');

export const formatDepthPrice = (price: number): string => depthPrice.format(price);
export const formatBandPrice = (price: number): string => bandPrice.format(price);
export const formatDepthNumber = (number: number): string => groupedNumber.format(number);

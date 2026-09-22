/** Market session the scanner reports (`mode` on `/api/mode` and every scanner
 * envelope); `loading` until the first one arrives. */
export type MarketMode = 'premarket' | 'market' | 'afterhours' | 'closed' | 'loading';

/** The Cryptos page's numbers and words (ADR 040). Thresholds mirror backend/constants_crypto.py. */
import type { CandleTf } from './types';

export const CRYPTOS_SCHEMA_VERSION = 1;
export const CRYPTO_BOARD_PATH = '/api/crypto/board';
export const CRYPTO_CANDLES_PATH = '/api/crypto/candles';
/** The page asks this often while it shows; the backend keeps each source on its own cadence. */
export const CRYPTO_BOARD_POLL_MS = 15_000;
/** While a source has not answered yet, ask again sooner. */
export const CRYPTO_BOARD_LOADING_POLL_MS = 3_000;
export const CRYPTO_CANDLES_POLL_MS = 30_000;
export const CRYPTO_CANDLES_LOADING_POLL_MS = 2_500;

/** Mirrors CRYPTO_FUNDING_CROWDED_PCT / CRYPTO_FUNDING_SHORTS_PCT: funding per 8 h. */
export const FUNDING_CROWDED_PCT = 0.03;
export const FUNDING_SHORTS_PCT = -0.01;
/** Mirrors CRYPTO_VOLUME_HOT_X. */
export const VOLUME_HOT_X = 2;
/** Mirrors CRYPTO_BRIDGE_READ_BAND_PT. */
export const BRIDGE_READ_BAND_PT = 0.5;
/** The Fear & Greed zones (alternative.me's own words). */
export const FEAR_GREED_ZONES = [
  { to: 25, label: 'Extreme fear', color: '#ff453a' },
  { to: 45, label: 'Fear', color: '#ff9f0a' },
  { to: 55, label: 'Neutral', color: '#98989d' },
  { to: 75, label: 'Greed', color: '#9bd65a' },
  { to: 100, label: 'Extreme greed', color: '#30d158' },
] as const;

export const CANDLE_TFS: readonly CandleTf[] = ['15m', '1h', '4h', '1d'];
export const CANDLE_TF_LABELS: Record<CandleTf, string> = { '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1D' };
/** The chart's quick picks; a coin picked in the table joins them. */
export const CHART_PICKS = ['BTC', 'ETH', 'SOL', 'DOGE'] as const;
export const CHART_DEFAULT = 'BTC';

export type CoinSort = 'cap' | 'movers' | 'volume' | 'tradeable';
export const COIN_SORTS: { id: CoinSort; label: string; tip: string }[] = [
  { id: 'cap', label: 'Top by cap', tip: 'Biggest first, by market value (price x coins in circulation).' },
  { id: 'movers', label: 'Movers 24h', tip: 'Biggest moves first, up or down, over the last 24 hours.' },
  { id: 'volume', label: 'Volume spikes', tip: 'Busiest against their own normal first: 24-hour volume over the 30-day average.' },
  { id: 'tradeable', label: 'Tradeable', tip: 'Only coins you can trade: IBKR lists the coin, or its ETF trades in Nova.' },
];
export type CoinGroup = 'all' | 'major' | 'layer1' | 'meme';
export const COIN_GROUPS: { id: CoinGroup; label: string; tip: string }[] = [
  { id: 'all', label: 'All', tip: 'Every coin on the board.' },
  { id: 'major', label: 'Majors', tip: 'The five biggest coins: they set the mood for everything else.' },
  { id: 'layer1', label: 'Layer 1', tip: 'Blockchains of their own (Ethereum, Solana, Cardano ...): the coin pays for using the network.' },
  { id: 'meme', label: 'Memes', tip: 'Coins that run on attention, not a product (Dogecoin, Pepe). Fast and crowded.' },
];

export const COLORS = {
  up: '#30d158',
  down: '#ff453a',
  warn: '#ff9f0a',
  cool: '#64d2ff',
  accent: '#0a84ff',
  muted: '#98989d',
  violet: '#bf5af2',
};

export const CRYPTOS_TITLE = 'Cryptos';
export const CRYPTOS_SUB = 'Crypto never closes. What’s moving, why, and the stocks it will move at the open.';
export const CRYPTOS_UNREADABLE = 'The crypto board answered something Nova could not read.';
export const CRYPTOS_OFF = 'The Cryptos page is switched off on this desk (NOVA_CRYPTO=0 in .env).';
export const CRYPTOS_OLD_API =
  'This backend has no Cryptos page yet -- restart it from an up-to-date checkout (Reload backend).';
export const CRYPTOS_REPLAY_NOTE = 'Live market -- the Sim replay does not apply here';

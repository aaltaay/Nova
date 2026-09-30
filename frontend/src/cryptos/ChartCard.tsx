/** The Cryptos page's chart card (ADR 040): a coin's Coinbase candles, its time frames and quick picks. */
import { CandleChart } from './CandleChart';
import { CANDLE_TF_LABELS, CANDLE_TFS, CHART_PICKS } from './constants';
import { level, pct, tone } from './format';
import { Card } from './parts';
import { tipChartLevel, tipCorr, tipEthBtc } from './tips/glossaryMarket';
import { useTip } from './tips/TipHost';
import type { CandleTf, CryptoBoard } from './types';
import { useCryptoCandles } from './useCryptoData';

export function ChartCard({ board, symbol, tf, onSymbol, onTf }: {
  board: CryptoBoard;
  symbol: string;
  tf: CandleTf;
  onSymbol: (s: string) => void;
  onTf: (tf: CandleTf) => void;
}) {
  const tip = useTip();
  const { data, error } = useCryptoCandles(symbol, tf);
  const coin = board.coins.find((c) => c.symbol === symbol);
  const shown = data && data.symbol === symbol && data.tf === tf ? data : null;
  const last = shown?.last ?? null;
  const ch = shown?.change_24h_pct ?? null;
  const abs = last !== null && ch !== null ? last - last / (1 + ch / 100) : null;
  const picks = CHART_PICKS.includes(symbol as (typeof CHART_PICKS)[number]) ? [...CHART_PICKS] : [...CHART_PICKS, symbol];
  const m = board.market;
  return (
    <Card
      title={`${symbol} · ${coin?.name ?? symbol}`}
      className="cx-chartcard"
      testId="crypto-chart-card"
      source={{ ids: ['coinbase'], label: 'Coinbase', sources: board.sources, now: board.clock.now }}
      head={
        <>
          <span className="cx-bigprice" {...(shown ? tip(() => tipChartLevel('last', shown, '')) : {})}>{level(last)}</span>
          <span className={`cx-strong cx-nowrap ${tone(ch)}`}>
            {abs === null ? '' : `${abs >= 0 ? '+' : '−'}${level(Math.abs(abs))} (${pct(ch)})`}
          </span>
          <div className="cx-seg" role="group" aria-label="Time frame">
            {CANDLE_TFS.map((t) => (
              <button key={t} type="button" aria-pressed={t === tf} className={t === tf ? 'is-active' : undefined} onClick={() => onTf(t)}
                {...tip(() => ({ title: `${CANDLE_TF_LABELS[t]} candles`, what: `Each candle is ${t === '15m' ? '15 minutes' : t === '1h' ? 'one hour' : t === '4h' ? 'four hours' : 'one day (00:00 UTC to 00:00 UTC)'}; the chart shows the last 96 of them.` }))}>
                {CANDLE_TF_LABELS[t]}
              </button>
            ))}
          </div>
        </>
      }
    >
      <div className="cx-chartcard__switch">
        {picks.map((s) => (
          <button key={s} type="button" className={`cx-pill${s === symbol ? ' is-active' : ''}`} onClick={() => onSymbol(s)}
            {...tip(() => ({ title: `Chart ${s}`, what: `Show ${s}’s Coinbase candles. Click any coin in the table to chart it too.` }))}>{s}</button>
        ))}
        <span className="cx-muted cx-small cx-push">
          <span {...tip(() => tipEthBtc(m))}>ETH/BTC {m.eth_btc === null ? '—' : m.eth_btc.toFixed(5)} <span className={tone(m.eth_btc_change_24h_pct)}>{pct(m.eth_btc_change_24h_pct, 1)}</span></span>
          {' · '}
          <span {...tip(() => tipCorr(m))}>30-day corr. to NQ {m.btc_qqq_corr_30d === null ? '—' : m.btc_qqq_corr_30d.toFixed(2)}</span>
        </span>
      </div>
      {shown && shown.candles.length > 1 ? (
        <CandleChart data={shown} />
      ) : (
        <div className="cx-chart-empty" role="status">
          {error ?? (shown?.error ? `Coinbase did not answer for ${symbol}: ${shown.error}` : `Loading Coinbase ${symbol}-USD …`)}
        </div>
      )}
    </Card>
  );
}

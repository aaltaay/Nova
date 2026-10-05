/**
 * The demo's sockets (ADR 043): a WebSocket stand-in that never connects to anything. Each one
 * opens in the page and is fed by a handler for its path: the HOD Momo feed (with a new alert
 * now and then), the setups board, and a symbol's detail, Level 2 and tape, which tick with the
 * symbol's sample market (liveMarket.ts). A path with no handler stays open and silent.
 */
import { tickerDetail } from './data/desk';
import { SIM_LAST, SIM_PLAYHEAD_MS, SIM_SYMBOL } from './data/sim';
import { demoVenue } from './demoApi';
import { iso, r2, sampleBook, sampleTape, type SamplePrint } from './data/market';
import { setupsBoard } from './data/pages';
import { bookWatch } from './data/read';
import { HOD_ALERTS, HOD_CONFIG } from './data/universe';
import { livePrice, watchMarket, type LiveState } from './liveMarket';

type Emit = (frame: unknown) => void;
type Handler = (m: RegExpMatchArray, emit: Emit) => (() => void) | void;

const EXCHANGES = ['NASDAQ', 'ARCA', 'EDGX', 'BATS', 'MEMX', 'IEX', 'NYSE', 'FINRA'];
const nowS = () => Date.now() / 1000;
const sym = (m: RegExpMatchArray) => decodeURIComponent(m[1]).toUpperCase();

function printFrame(symbol: string, p: SamplePrint, i: number) {
  return {
    type: 'print', symbol, time: iso(p.ms), price: p.price, size: p.size, exchange: EXCHANGES[(i * 3) % EXCHANGES.length],
    conditions: p.size < 100 ? 'I' : '', unreported: false, sets_price: p.size >= 100, side: p.side, bid: p.bid, ask: p.ask,
    ts: p.ms / 1000, ts_source: 'receive', exchange_ts: Math.floor(p.ms / 1000), source: 'ibkr',
  };
}

function bookFrame(s: LiveState) {
  const rows = (side: 'bid' | 'ask') => (side === 'bid' ? s.bids : s.asks).slice(0, 14).map((r) => ({ price: r.price, size: r.size, side, mm: r.mm }));
  return { type: 'book', symbol: s.symbol, data: { l1_fallback: false, bids: rows('bid'), asks: rows('ask') } };
}

/** A Level 2 line's versions, as the backend stamps them (ADR 045): each book `seq` / `at` / `sent`,
 *  and a `beat` every 250 ms with the newest, so the demo's ladder reads live, never behind. */
function versionedLine(symbol: string, emit: Emit): { book: (frame: ReturnType<typeof bookFrame>) => void; stop: () => void } {
  let seq = 0;
  let at: number | null = null;
  const timer = setInterval(() => emit({ type: 'beat', symbol, seq, at, now: nowS() }), 250);
  return {
    book: (frame) => {
      seq += 1;
      at = nowS();
      emit({ ...frame, seq, at, sent: nowS() });
    },
    stop: () => clearInterval(timer),
  };
}

const quoteSeq = new Map<string, number>();

/** A new HOD Momo alert every ~50 s, on a name already running, at its price now. */
function alertsEvery(emit: Emit): () => void {
  const names = ['RUNR', 'SPIK', 'GAPX', 'FLTX', 'MMTX', 'HODX'];
  const strategies = Object.values(HOD_CONFIG.strategies);
  let n = 0;
  const timer = setInterval(() => {
    const base = HOD_ALERTS.find((a) => a.ticker === names[n % names.length]) ?? HOD_ALERTS[0];
    const strat = strategies[n % strategies.length];
    const ms = Date.now();
    const price = livePrice(base.ticker);
    n += 1;
    emit({
      type: 'alert',
      alert: {
        ...base, id: `${ms}-${base.ticker}-${strat.strategy_id}`, consolidated_ids: [`${ms}-${base.ticker}-${strat.strategy_id}`],
        timestamp: iso(ms), created_ts: ms / 1000, price, strategy_id: strat.strategy_id, strategy_name: strat.name,
        strategies: undefined, consolidation_count: 1, consolidation_span_sec: null,
      },
    });
  }, 50_000);
  return () => clearInterval(timer);
}

const HANDLERS: [RegExp, Handler][] = [
  [/^\/ws\/hod-momo/, (_m, emit) => {
    emit({ type: 'initial', alerts: HOD_ALERTS, total: 47 });
    return alertsEvery(emit);
  }],
  [/^\/ws\/setups/, (_m, emit) => {
    emit(setupsBoard(nowS()));
  }],
  [/^\/ws\/ticker\/([^/?]+)/, (m, emit) => {
    const symbol = sym(m);
    emit({ type: 'initial', ...tickerDetail(symbol) });
    if (demoVenue() === 'sim') return undefined; // the replay is paused at its playhead
    const live = watchMarket(symbol, {
      print: (p, s) => {
        const seq = (quoteSeq.get(symbol) ?? 0) + 1;
        quoteSeq.set(symbol, seq);
        emit({ type: 'trade_update', symbol, price: p.price, size: p.size, timestamp: iso(p.ms), volume: s.dayVolume, source: 'stream', seq, at: nowS() });
      },
    });
    return live.stop;
  }],
  [/^\/ws\/ibkr\/depth\/([^/?]+)/, (m, emit) => {
    const symbol = sym(m);
    emit({ type: 'subscribed', symbol, instance: 'nova-demo' });
    const line = versionedLine(symbol, emit);
    if (demoVenue() === 'sim') {
      // The replay's recorded book at the playhead; any other symbol has none.
      if (symbol === SIM_SYMBOL) {
        const book = sampleBook(SIM_LAST, 5);
        line.book(bookFrame({ symbol, last: SIM_LAST, bid: r2(SIM_LAST - 0.01), ask: SIM_LAST, dayVolume: 0, ...book }));
      }
      return line.stop;
    }
    const live = watchMarket(symbol, { book: (s) => line.book(bookFrame(s)) });
    line.book(bookFrame(live.state));
    if (symbol === 'SMPL') emit(bookWatch(nowS()));
    return () => {
      live.stop();
      line.stop();
    };
  }],
  [/^\/ws\/ibkr\/tape\/([^/?]+)/, (m, emit) => {
    const symbol = sym(m);
    let i = 0;
    emit({ type: 'subscribed', symbol });
    if (demoVenue() === 'sim') {
      if (symbol === SIM_SYMBOL) for (const p of sampleTape(90, SIM_PLAYHEAD_MS, SIM_LAST)) emit(printFrame(symbol, p, (i += 1)));
      return undefined;
    }
    const live = watchMarket(symbol, { print: (p) => emit(printFrame(symbol, p, (i += 1))) });
    // The morning's last prints, ending a moment ago, then the live ones.
    for (const p of sampleTape(90, Date.now(), live.state.last)) emit(printFrame(symbol, p, (i += 1)));
    return live.stop;
  }],
];

/** Start the handler for a socket path; returns its stop function (a no-op for a silent path). */
export function attachSocket(path: string, emit: Emit): () => void {
  for (const [re, fn] of HANDLERS) {
    const m = path.match(re);
    if (m) return fn(m, emit) ?? (() => {});
  }
  return () => {};
}

type Listener = ((ev: Event) => void) | null;

/** A WebSocket that lives in the page: it opens, takes the frames its path's handler sends, and closes. */
export class DemoSocket extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readonly url: string;
  readyState = 0;
  protocol = '';
  extensions = '';
  binaryType: BinaryType = 'blob';
  bufferedAmount = 0;
  onopen: Listener = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: Listener = null;
  private stop: () => void = () => {};

  constructor(url: string | URL) {
    super();
    this.url = String(url);
    setTimeout(() => this.open(), 20);
  }

  private open(): void {
    if (this.readyState !== 0) return;
    this.readyState = 1;
    const ev = new Event('open');
    this.onopen?.(ev);
    this.dispatchEvent(ev);
    const path = new URL(this.url, 'http://demo.invalid').pathname;
    this.stop = attachSocket(path, (frame) => this.deliver(frame));
  }

  private deliver(frame: unknown): void {
    if (this.readyState !== 1) return;
    const ev = new MessageEvent('message', { data: typeof frame === 'string' ? frame : JSON.stringify(frame) });
    this.onmessage?.(ev);
    this.dispatchEvent(ev);
  }

  /** Whatever the desk sends (subscriptions, pings) is taken and dropped. */
  send(): void {
    if (this.readyState === 0) throw new DOMException('The socket is still connecting.', 'InvalidStateError');
  }

  close(code = 1000, reason = ''): void {
    if (this.readyState >= 2) return;
    this.readyState = 2;
    this.stop();
    setTimeout(() => {
      this.readyState = 3;
      const ev = new CloseEvent('close', { code, reason, wasClean: true });
      this.onclose?.(ev);
      this.dispatchEvent(ev);
    }, 0);
  }
}

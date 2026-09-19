import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { useWorkspace } from '../workspace';
import { emitSimClockScrub } from './simClockEvents';
import { previousEtWeekday } from './historicalReplayFormat';
import { SIM_HISTORY_POLL_MS, SIM_SESSION_CLOSE_LABEL, SIM_SESSION_OPEN_LABEL } from './simConstants';

type Job = { id: string; symbol: string; date: string; start: string; end: string;
  kind: string; status: string; count: number; pages: number; error: string | null };

function jobLabel(j: Job): string {
  return `${j.symbol} ${j.date} ${j.start}–${j.end} ${j.kind}`;
}

export function HistoricalReplayPanel() {
  const { openStockView } = useWorkspace();
  const [symbol, setSymbol] = useState('');
  const [date, setDate] = useState(() => previousEtWeekday());
  const dateTouched = useRef(false);
  const [start, setStart] = useState(SIM_SESSION_OPEN_LABEL);
  const [end, setEnd] = useState(SIM_SESSION_CLOSE_LABEL);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const spec = { symbol: symbol.trim().toUpperCase(), date, start, end };
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const res = await novaFetch(`${API_BASE_URL}/api/sim/history`);
        if (!res.ok) return;
        const data = await res.json();
        if (!active) return;
        // Guard the shape: an unexpected body must never unmount the SIM header.
        setJobs(Array.isArray(data?.jobs) ? data.jobs : []);
        if (typeof data?.default_date === 'string' && !dateTouched.current) setDate(data.default_date);
      } catch { /* Action errors below remain visible; polling can recover. */ }
    }
    void refresh(); const id = window.setInterval(() => void refresh(), SIM_HISTORY_POLL_MS);
    return () => { active = false; window.clearInterval(id); };
  }, []);
  async function request(path: string, body?: unknown) {
    setBusy(true); setError('');
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/history${path}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body ?? {}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Historical replay request failed');
      return data;
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function load() {
    if (await request('/select', spec)) {
      openStockView(spec.symbol); emitSimClockScrub();
      setMessage(`Loaded ${spec.symbol} · ${date} · ${start}–${end} ET. Candles appear at interval close; downloaded trades build partial candles. Download candles if this window is not stored yet.`);
    }
  }
  const pickDate = (value: string) => { dateTouched.current = true; setDate(value); };
  return <details style={{ position: 'relative' }}>
    <summary>Historical replay</summary>
    <section aria-label="Historical replay setup" style={{ position: 'absolute', right: 0,
      top: 25, width: 550, maxWidth: '90vw', zIndex: 1000, padding: 16,
      background: '#20232c', border: '1px solid #8060b0', boxShadow: '0 4px 20px #0008' }}>
      <p>Replay any supported stock ticker. Times are America/New_York.</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <label>Ticker <input aria-label="Historical ticker" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} size={8} /></label>
        <label>Date <input type="date" value={date} onChange={e => pickDate(e.target.value)} /></label>
        <label>From <input type="time" value={start} onChange={e => setStart(e.target.value)} /></label>
        <label>To <input type="time" value={end} onChange={e => setEnd(e.target.value)} /></label>
      </div>
      <p style={{ display: 'flex', gap: 8 }}>
        <button disabled={busy || !symbol} onClick={() => void load()}>Load replay</button>
        <button disabled={busy || !symbol} onClick={() => void request('', { ...spec, kind: 'bars' })}>Download candles</button>
        <button disabled={busy || !symbol} onClick={() => void request('', { ...spec, kind: 'trades' })}>Download trades</button>
      </p>
      <p>Load replay again after downloading to use the new data; the playhead stays where it is. Historical quotes and Level 2 are unavailable.</p>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" style={{ color: '#ff938c' }}>{error}</p>}
      <ul aria-label="Historical downloads" style={{ maxHeight: 240, overflow: 'auto', listStyle: 'none', padding: 0 }}>{jobs.map(j => <li key={j.id} aria-label={jobLabel(j)} style={{ padding: '8px 0', borderTop: '1px solid #555' }}>
        <strong>{j.symbol} · {j.date} · {j.start}–{j.end}</strong>
        <div>{j.kind}: {j.status} · {j.count.toLocaleString()} {j.kind === 'trades' ? 'prints' : 'candles'} · {j.pages} pages</div>
        <button disabled={busy} aria-label={`Use this window: ${jobLabel(j)}`} onClick={() => {
          setSymbol(j.symbol); pickDate(j.date); setStart(j.start); setEnd(j.end);
        }}>Use this window</button>
        {j.error && <p role="alert">{j.error}</p>}
        {j.status === 'pause_requested'
          ? <button disabled aria-label={`Pausing download: ${jobLabel(j)}`}>Pausing…</button>
          : j.status !== 'complete' && <button disabled={busy}
            aria-label={`${j.status === 'running' ? 'Pause' : 'Resume'} download: ${jobLabel(j)}`}
            onClick={() => void request(`/${j.id}/${j.status === 'running' ? 'pause' : 'resume'}`)}>
            {j.status === 'running' ? 'Pause download' : 'Resume download'}
          </button>}
      </li>)}</ul>
    </section>
  </details>;
}

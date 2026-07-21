import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';

const API = `${API_BASE_URL}/api`;

export function BlocklistPanel() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [input, setInput] = useState('');

  useEffect(() => {
    fetch(`${API}/hod-momo/blocklist`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.symbols) setSymbols(data.symbols); })
      .catch((err) => {
        console.error('HOD blocklist fetch failed', err);
      });
  }, []);

  const add = useCallback(() => {
    const sym = input.trim().toUpperCase();
    if (!sym || symbols.includes(sym)) return;
    novaFetch(`${API}/hod-momo/blocklist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: sym }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.symbols) setSymbols(data.symbols); });
    setInput('');
  }, [input, symbols]);

  const remove = useCallback((sym: string) => {
    novaFetch(`${API}/hod-momo/blocklist/${sym}`, { method: 'DELETE' })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.symbols) setSymbols(data.symbols); });
  }, []);

  return (
    <div className="hod-blocklist-panel">
      <div className="hod-cfg-section-header">
        <span className="hod-cfg-section-title">Global Blocklist</span>
      </div>
      <p className="hod-cfg-hint">Blocked tickers are excluded from every scanner (Gappers, Movers, After-Hours, News Catalysts) and HOD Momo alerts.</p>
      <div className="hod-momo-list">
        {symbols.map(sym => (
          <span key={sym} className="hod-momo-tag hod-block-tag">
            {sym}
            <button className="hod-momo-tag-remove" onClick={() => remove(sym)}>×</button>
          </span>
        ))}
        {symbols.length === 0 && <span className="na-muted">No blocked tickers</span>}
      </div>
      <div className="hod-momo-add-row">
        <input
          className="hod-cfg-input hod-momo-input"
          type="text"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          placeholder="Ticker to block…"
          onKeyDown={e => e.key === 'Enter' && add()}
        />
        <button className="hod-cfg-btn" onClick={add}>Block</button>
      </div>
    </div>
  );
}

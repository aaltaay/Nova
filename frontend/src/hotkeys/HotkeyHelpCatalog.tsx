/**
 * Capability / compatibility help — what could be built, with evidence badges.
 */

import { useMemo, useState } from 'react';
import { formatKeyChord } from './htkFormat';
import { createDefaultNovaActions } from './novaActionDefaults';
import { HOTKEY_CAPABILITY_CATALOG } from './capabilityCatalog';
import {
  HOTKEY_CAPABILITY_CATEGORIES,
  HOTKEY_COMPAT_LABELS,
  HOTKEY_EVIDENCE_LABELS,
  type HotkeyCapabilityCategory,
  type HotkeyCompatStatus,
  type HotkeyEvidenceLevel,
} from './types';

interface Props {
  onClose: () => void;
}

export function HotkeyHelpCatalog({ onClose }: Props) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<HotkeyCapabilityCategory | 'all'>('all');
  const [status, setStatus] = useState<HotkeyCompatStatus | 'all'>('all');

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return HOTKEY_CAPABILITY_CATALOG.filter((e) => {
      if (category !== 'all' && e.category !== category) return false;
      if (status !== 'all' && e.status !== status) return false;
      if (!q) return true;
      return (
        e.label.toLowerCase().includes(q)
        || e.description.toLowerCase().includes(q)
        || (e.example?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [query, category, status]);

  return (
    <div className="hotkey-help">
      <div className="hotkey-help-header">
        <h3 className="nova-os-section-title">Hotkey capability help</h3>
        <button type="button" className="btn-secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="na-muted">
        Compatibility (can Nova support this later?) is separate from evidence
        (is this a verified DAS command vs community recipe). Phase G3 ships typed
        Nova Actions (not raw DAS scripts) — see defaults below.
      </p>

      <div className="nova-defaults-help">
        <h4 className="nova-os-section-title">Curated Nova defaults (DAS-inspired)</h4>
        <ul className="executor-hotkeys-list">
          {createDefaultNovaActions().map((a) => (
            <li key={a.id}>
              <kbd>{formatKeyChord(a.key)}</kbd>
              <span>{a.name}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="hotkey-help-filters">
        <input
          type="search"
          placeholder="Search capabilities…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search capabilities"
        />
        <select
          value={category}
          onChange={(e) =>
            setCategory(e.target.value as HotkeyCapabilityCategory | 'all')
          }
          aria-label="Filter by category"
        >
          <option value="all">All categories</option>
          {HOTKEY_CAPABILITY_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as HotkeyCompatStatus | 'all')}
          aria-label="Filter by status"
        >
          <option value="all">All statuses</option>
          {(Object.keys(HOTKEY_COMPAT_LABELS) as HotkeyCompatStatus[]).map((s) => (
            <option key={s} value={s}>
              {HOTKEY_COMPAT_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
      <ul className="hotkey-help-list">
        {rows.map((e) => (
          <li key={e.id} className="hotkey-help-item">
            <div className="hotkey-help-item-title">
              <strong>{e.label}</strong>
              <span className={`hotkey-badge hotkey-badge-${e.status}`}>
                {HOTKEY_COMPAT_LABELS[e.status]}
              </span>
              <span className="hotkey-badge hotkey-badge-evidence">
                {HOTKEY_EVIDENCE_LABELS[e.evidence as HotkeyEvidenceLevel]}
              </span>
            </div>
            <p>{e.description}</p>
            {e.example && (
              <code className="hotkey-help-example">{e.example}</code>
            )}
            {e.safetyNote && (
              <p className="hotkey-help-safety">{e.safetyNote}</p>
            )}
          </li>
        ))}
      </ul>
      {rows.length === 0 && (
        <p className="na-muted">No capabilities match this filter.</p>
      )}
    </div>
  );
}

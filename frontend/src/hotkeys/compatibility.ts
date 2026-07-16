/**
 * Classify DAS hotkey rows for Nova/IBKR portability.
 * Compatibility status ≠ evidence confidence (tracked separately).
 */

import { HOTKEY_DEFAULTS, type HotkeyAction, type HotkeyBinding } from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';
import { tokenizeDasCommand } from './dasCommandParser';
import type {
  DasCommandToken,
  HotkeyCompatStatus,
  HotkeyDiagnostic,
  HotkeyEvidenceLevel,
  HotkeyKeyChord,
  HotkeyRecord,
  HotkeyRecordAnalysis,
} from './types';

const TRANSLATABLE_ASSIGNMENTS = new Set([
  'SHARE',
  'PRICE',
  'ROUTE',
  'TIF',
  'ACCOUNT',
  'STOPTYPE',
  'STOPPRICE',
  'DEFSHARE',
  'SSHARE',
]);

const BACKEND_ASSIGNMENTS = new Set([
  'TRIGGERORDER',
  'WITHTRIGGER',
  'LOWPRICE',
  'HIGHPRICE',
]);

const COMMUNITY_ACTIONS = new Set(['REVERSE']);

function chordMatchesBinding(chord: HotkeyKeyChord, binding: HotkeyBinding): boolean {
  if (!chord.key) return false;
  if (chord.key.toLowerCase() !== binding.key.toLowerCase()) return false;
  return (
    Boolean(chord.ctrl) === Boolean(binding.ctrl)
    && Boolean(chord.shift) === Boolean(binding.shift)
    && Boolean(chord.alt) === Boolean(binding.alt)
    && Boolean(chord.meta) === Boolean(binding.meta)
  );
}

/** Return Nova action IDs whose defaults conflict with this chord. */
export function findNovaKeyConflicts(chord: HotkeyKeyChord): string[] {
  const hits: string[] = [];
  for (const action of Object.keys(HOTKEY_DEFAULTS) as HotkeyAction[]) {
    if (chordMatchesBinding(chord, HOTKEY_DEFAULTS[action])) {
      hits.push(action);
    }
  }
  return hits;
}

export function formatNovaConflictLabel(action: string): string {
  const binding = HOTKEY_DEFAULTS[action as HotkeyAction];
  if (!binding) return action;
  return `${action} (${formatHotkeyLabel(binding)})`;
}

function tokenEvidence(token: DasCommandToken): HotkeyEvidenceLevel {
  const name = token.name.toUpperCase();
  if (token.kind === 'url') return 'das_verified';
  if (token.kind === 'cancel') return 'community_version_sensitive';
  if (token.kind === 'focus') return 'community_version_sensitive';
  if (token.kind === 'trigger') return 'das_verified';
  if (token.kind === 'action') {
    if (name === 'BUY' || name === 'SELL' || name.startsWith('NEWORDER')) return 'das_verified';
    if (name === 'SEND' && token.value && COMMUNITY_ACTIONS.has(token.value.toUpperCase())) {
      return 'community_version_sensitive';
    }
    if (name === 'SEND' || name === 'LOAD') return 'das_verified';
  }
  if (token.kind === 'assignment') {
    if (name === 'SHARE' && token.value && /pos\s*\*/i.test(token.value)) {
      return 'community_version_sensitive';
    }
    if (name === 'PRICE' && token.value && /mid/i.test(token.value)) {
      return 'community_version_sensitive';
    }
    if (TRANSLATABLE_ASSIGNMENTS.has(name) || BACKEND_ASSIGNMENTS.has(name)) {
      return 'das_verified';
    }
  }
  return 'community_version_sensitive';
}

function worstEvidence(levels: HotkeyEvidenceLevel[]): HotkeyEvidenceLevel {
  if (levels.includes('community_version_sensitive')) return 'community_version_sensitive';
  if (levels.includes('documented_workflow')) return 'documented_workflow';
  return 'das_verified';
}

function classifyTokens(tokens: DasCommandToken[]): {
  status: HotkeyCompatStatus;
  diagnostics: HotkeyDiagnostic[];
  evidence: HotkeyEvidenceLevel;
} {
  const diagnostics: HotkeyDiagnostic[] = [];
  if (tokens.length === 0) {
    return {
      status: 'invalid_unsafe',
      evidence: 'das_verified',
      diagnostics: [{ code: 'empty_command', message: 'Command is empty' }],
    };
  }

  let hasBackend = false;
  let hasTranslatable = false;
  let hasDasSpecific = false;
  const hasInvalid = false;
  const evidenceLevels: HotkeyEvidenceLevel[] = [];

  for (const token of tokens) {
    const evidence = tokenEvidence(token);
    evidenceLevels.push(evidence);

    if (token.kind === 'unknown') {
      hasDasSpecific = true;
      diagnostics.push({
        code: 'unknown_token',
        message: `Unrecognized segment preserved: ${token.raw}`,
        evidence,
      });
      continue;
    }

    if (token.kind === 'url' || token.kind === 'focus') {
      hasDasSpecific = true;
      diagnostics.push({
        code: token.kind === 'url' ? 'url_action' : 'focus_action',
        message:
          token.kind === 'url'
            ? 'External URL / symbol link — DAS workspace action'
            : 'Window focus command — DAS/version-sensitive',
        evidence,
      });
      continue;
    }

    if (token.kind === 'cancel') {
      hasTranslatable = true;
      diagnostics.push({
        code: 'cancel_scope',
        message: 'Cancel scope — syntax is community/version-sensitive',
        evidence,
      });
      continue;
    }

    if (token.kind === 'trigger') {
      hasBackend = true;
      diagnostics.push({
        code: 'linked_order',
        message: 'Trigger/OTO linked order — needs Nova linked-order support',
        evidence,
      });
      continue;
    }

    if (token.kind === 'action') {
      const name = token.name.toUpperCase();
      const val = (token.value ?? '').toUpperCase();
      if (name === 'SEND' && val === 'REVERSE') {
        hasTranslatable = true;
        diagnostics.push({
          code: 'reverse',
          message: 'Send=Reverse — community flatten/cover pattern; validate before use',
          evidence,
        });
        continue;
      }
      if (name === 'BUY' || name === 'SELL' || name === 'SEND' || name === 'LOAD') {
        hasTranslatable = true;
        continue;
      }
      if (name.startsWith('NEWORDER')) {
        hasBackend = true;
        diagnostics.push({
          code: 'chart_new_order',
          message: 'Chart NewOrder — needs chart-context order support',
          evidence,
        });
        continue;
      }
    }

    if (token.kind === 'assignment') {
      const name = token.name.toUpperCase();
      if (BACKEND_ASSIGNMENTS.has(name)) {
        hasBackend = true;
        continue;
      }
      if (name === 'ROUTE') {
        const route = (token.value ?? '').toUpperCase();
        if (route && !['LIMIT', 'MARKET', 'STOP', 'SMRTL', 'SMRTM', 'SMART'].includes(route)) {
          hasDasSpecific = true;
          diagnostics.push({
            code: 'direct_route',
            message: `Route ${token.value} may be DAS/broker-specific (Nova uses IBKR SMART)`,
            evidence: 'das_verified',
          });
        } else {
          hasTranslatable = true;
        }
        continue;
      }
      if (name === 'SHARE' && token.value && /BP|DefShare/i.test(token.value)) {
        hasBackend = true;
        diagnostics.push({
          code: 'bp_sizing',
          message: 'Buying-power / DefShare sizing — community workflow, needs risk engine',
          evidence: 'community_version_sensitive',
        });
        continue;
      }
      if (TRANSLATABLE_ASSIGNMENTS.has(name)) {
        hasTranslatable = true;
        continue;
      }
      hasDasSpecific = true;
      diagnostics.push({
        code: 'unknown_assignment',
        message: `Assignment preserved: ${token.name}=${token.value ?? ''}`,
        evidence,
      });
    }
  }

  // Priority: invalid > backend > das-specific > translatable
  let status: HotkeyCompatStatus = 'translatable_later';
  if (hasInvalid) status = 'invalid_unsafe';
  else if (hasBackend) status = 'backend_required';
  else if (hasDasSpecific && !hasTranslatable) status = 'das_ibkr_specific';
  else if (hasDasSpecific && hasTranslatable) status = 'backend_required';
  else if (hasTranslatable) status = 'translatable_later';
  else status = 'das_ibkr_specific';

  return { status, diagnostics, evidence: worstEvidence(evidenceLevels) };
}

export function analyzeRecord(
  record: HotkeyRecord,
  allRecords: HotkeyRecord[],
): HotkeyRecordAnalysis {
  const tokens = tokenizeDasCommand(record.command);
  const { status, diagnostics, evidence } = classifyTokens(tokens);
  const conflictsWithNova = findNovaKeyConflicts(record.key);
  const duplicateKeyIds = allRecords
    .filter(
      (r) =>
        r.id !== record.id
        && r.key.label
        && record.key.label
        && r.key.label.toLowerCase() === record.key.label.toLowerCase(),
    )
    .map((r) => r.id);

  const diags = [...diagnostics];
  if (conflictsWithNova.length) {
    diags.push({
      code: 'nova_key_conflict',
      message: `Key conflicts with active Nova shortcut(s): ${conflictsWithNova
        .map(formatNovaConflictLabel)
        .join(', ')}`,
      evidence: 'das_verified',
    });
  }
  if (duplicateKeyIds.length) {
    diags.push({
      code: 'duplicate_key',
      message: 'Duplicate key within this hotkey profile',
      evidence: 'das_verified',
    });
  }

  let finalStatus = status;
  if (!record.key.key && !record.key.label) {
    finalStatus = 'invalid_unsafe';
    diags.push({ code: 'missing_key', message: 'No key assigned' });
  }

  return {
    recordId: record.id,
    status: finalStatus,
    evidence,
    tokens,
    diagnostics: diags,
    conflictsWithNova: conflictsWithNova.length ? conflictsWithNova : undefined,
    duplicateKeyIds: duplicateKeyIds.length ? duplicateKeyIds : undefined,
  };
}

export function analyzeProfile(records: HotkeyRecord[]): HotkeyRecordAnalysis[] {
  return records.map((r) => analyzeRecord(r, records));
}

export interface CompatSummary {
  nova_active: number;
  translatable_later: number;
  backend_required: number;
  das_ibkr_specific: number;
  invalid_unsafe: number;
  conflicts: number;
}

export function summarizeAnalyses(analyses: HotkeyRecordAnalysis[]): CompatSummary {
  const summary: CompatSummary = {
    nova_active: 0,
    translatable_later: 0,
    backend_required: 0,
    das_ibkr_specific: 0,
    invalid_unsafe: 0,
    conflicts: 0,
  };
  for (const a of analyses) {
    summary[a.status] += 1;
    if (a.conflictsWithNova?.length || a.duplicateKeyIds?.length) {
      summary.conflicts += 1;
    }
  }
  return summary;
}

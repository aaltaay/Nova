/**
 * DAS-compatible hotkey manager types (Phase G2) + Nova Actions (Phase G3).
 * Imported DAS records stay inactive until mapped to a typed Nova Action.
 */

import type { HotkeyAction } from '../constants';
import type { NovaActionRecord } from './novaActionTypes';

export const HOTKEY_PROFILE_SCHEMA_VERSION = 3 as const;

export const HOTKEY_COMPAT_STATUSES = [
  'nova_active',
  'translatable_later',
  'backend_required',
  'das_ibkr_specific',
  'invalid_unsafe',
] as const;

export type HotkeyCompatStatus = (typeof HOTKEY_COMPAT_STATUSES)[number];

export const HOTKEY_EVIDENCE_LEVELS = [
  'das_verified',
  'documented_workflow',
  'community_version_sensitive',
] as const;

export type HotkeyEvidenceLevel = (typeof HOTKEY_EVIDENCE_LEVELS)[number];

export const HOTKEY_CAPABILITY_CATEGORIES = [
  'sizing',
  'pricing',
  'order_type',
  'route_tif',
  'intent',
  'cancel',
  'linked_orders',
  'workspace',
  'composite',
  'automation',
] as const;

export type HotkeyCapabilityCategory = (typeof HOTKEY_CAPABILITY_CATEGORIES)[number];

export interface HotkeyKeyChord {
  /** DAS-style display string, e.g. "Shift+1", "ESC", "Alt+3". */
  label: string;
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
}

export interface HotkeyRecord {
  id: string;
  name: string;
  key: HotkeyKeyChord;
  /** Original DAS command text — preserved for round-trip export. */
  command: string;
  /** True when the user edited the command after import. */
  commandEdited?: boolean;
}

export interface HotkeyDiagnostic {
  code: string;
  message: string;
  evidence?: HotkeyEvidenceLevel;
}

export interface HotkeyRecordAnalysis {
  recordId: string;
  status: HotkeyCompatStatus;
  evidence: HotkeyEvidenceLevel;
  tokens: DasCommandToken[];
  diagnostics: HotkeyDiagnostic[];
  conflictsWithNova?: string[];
  duplicateKeyIds?: string[];
}

export interface HotkeyProfile {
  schemaVersion: typeof HOTKEY_PROFILE_SCHEMA_VERSION;
  /** Display name of the last loaded/saved .htk file. */
  fileName: string;
  records: HotkeyRecord[];
  /** Typed executable actions (Phase G3). */
  novaActions: NovaActionRecord[];
  /** Optional overrides for Automation six (Phase G / rebind-on-the-go). */
  automationBindings?: Partial<Record<HotkeyAction, HotkeyKeyChord>>;
  /** Optional override for the shortcuts cheat-sheet chord (default Ctrl+M). */
  shortcutsMenuKey?: HotkeyKeyChord;
  updatedAt: string;
}

export interface HtkParseIssue {
  line: number;
  message: string;
  raw?: string;
}

export interface HtkParseResult {
  records: HotkeyRecord[];
  issues: HtkParseIssue[];
}

export type DasCommandTokenKind =
  | 'assignment'
  | 'action'
  | 'cancel'
  | 'url'
  | 'focus'
  | 'trigger'
  | 'unknown';

export interface DasCommandToken {
  raw: string;
  kind: DasCommandTokenKind;
  /** Left-hand side for assignments, or the action verb. */
  name: string;
  value?: string;
}

export interface HotkeyCapabilityEntry {
  id: string;
  category: HotkeyCapabilityCategory;
  label: string;
  description: string;
  example?: string;
  evidence: HotkeyEvidenceLevel;
  status: HotkeyCompatStatus;
  safetyNote?: string;
}

export const HOTKEY_COMPAT_LABELS: Record<HotkeyCompatStatus, string> = {
  nova_active: 'Nova active',
  translatable_later: 'Translatable later',
  backend_required: 'Backend required',
  das_ibkr_specific: 'DAS/IBKR-specific',
  invalid_unsafe: 'Invalid / unsafe',
};

export const HOTKEY_EVIDENCE_LABELS: Record<HotkeyEvidenceLevel, string> = {
  das_verified: 'DAS verified',
  documented_workflow: 'Documented workflow',
  community_version_sensitive: 'Community / version-sensitive',
};

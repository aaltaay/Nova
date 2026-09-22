/** `GET /api/diagnostics` (ADR 021; AGENTS.md §3 "Desk diagnostics"). */

export type DiagState = 'ok' | 'warn' | 'fail' | 'off' | 'unknown';

export type DiagActionKind = 'reconnect_ibkr' | 'launch_gateway' | 'reload_backend' | 'refresh';

export interface DiagAction {
  kind: DiagActionKind | string;
  label: string;
}

export interface DiagRow {
  id: string;
  group: string;
  title: string;
  state: DiagState | string;
  detail: string;
  cause: string;
  fix: string;
  since: number | null;
  action: DiagAction | null;
  evidence: Record<string, unknown> | null;
}

export interface DiagGroup {
  id: string;
  title: string;
}

export interface DiagnosticsPayload {
  schema_version: number;
  generated_at: string | number;
  groups: DiagGroup[];
  counts: Partial<Record<DiagState, number>>;
  rows: DiagRow[];
}

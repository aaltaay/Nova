/** Wire shapes of `/api/setups/templates` (backend `setup_templates/`, ADR 029). */

export type ParamKind = 'number' | 'int' | 'bool' | 'time' | 'choice';
export type ParamValue = number | boolean | string | null;

export interface ParamSpec {
  key: string;
  group: string;
  label: string;
  kind: ParamKind;
  default: ParamValue;
  unit: string;
  min: number | string | null;
  max: number | string | null;
  step: number | null;
  choices: { value: string; label: string }[];
  /** Off when null (a stock filter). */
  nullable: boolean;
  help: string;
  /** A running scanner reads it (false: kept for when the setup gets a scanner). */
  live: boolean;
}

export interface ParamGroup {
  id: string;
  label: string;
  blurb: string;
  params: ParamSpec[];
}

export interface SetupCatalogue {
  setup: string;
  scanner: boolean;
  source: string;
  groups: ParamGroup[];
}

export interface TemplateReadout {
  state: string;
  passed: boolean;
  reason: string | null;
  go_triggered: number | null;
  min_go: number | null;
  go_avg_net_r: number | null;
  /** ADR 031: the control group (blind / wait) and the bar go must clear. Absent on an older API. */
  control_avg_net_r?: number | null;
  control_triggered?: number | null;
  min_net_r?: number | null;
}

export interface SetupTemplate {
  id: string;
  setup: string;
  name: string;
  note: string;
  rev: number;
  values: Record<string, ParamValue>;
  builtin: boolean;
  in_play: boolean;
  fingerprint: string;
  /** Set when the stored rules no longer validate: shown, editable, never run. */
  error: string | null;
  created_at: number | null;
  updated_at: number | null;
  readout?: TemplateReadout | null;
}

export interface SetupTemplates {
  id: string;
  scanner: boolean;
  catalogue: SetupCatalogue;
  in_play: string;
  templates: SetupTemplate[];
}

export interface TemplatesPayload {
  schema_version: number;
  error: string | null;
  max_per_setup: number;
  setups: SetupTemplates[];
}

/** A refusal from the templates API: the words, and the parameter it names. */
export class TemplateApiError extends Error {
  field: string | null;
  code: string | null;

  constructor(message: string, field: string | null = null, code: string | null = null) {
    super(message);
    this.field = field;
    this.code = code;
  }
}

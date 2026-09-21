/** Shared response from the process-local Sim clock endpoint. */
export interface SimClockState {
  sim: boolean;
  sim_time_et?: string;
  /** Eastern session date (YYYY-MM-DD); the last open exchange day on weekends/holidays. */
  session_date?: string;
  session_open_et?: string;
  session_close_et?: string;
  phase?: string;
  minute_from_open?: number;
  minute_max?: number;
  scrubbed?: boolean;
  paused?: boolean;
  replay_date?: string | null;
  replay_symbol?: string | null;
  replay_source?: string;
  replay_ok?: boolean;
  replay_error?: string | null;
  replay_load?: {
    l2_total: number; l2_loaded: number; l2_decimated: boolean;
    malformed_rows: number; invalid_timestamp_rows: number; invalid_rows: number;
    legacy_schema: boolean;
    /** Recorded stretches of a capture, with why each ended (manifest segments). */
    segments?: CaptureSegment[];
  };
}

export interface CaptureSegment {
  started_et: string;
  stopped_et: string | null;
  status?: string;
  reason?: string | null;
  counts?: Record<string, number>;
}

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
  /**
   * The playhead is now: following the wall clock on today's date, inside the
   * session -- not paused, not scrubbed, no past day loaded (ADR 020 live-edge
   * amendment). At the edge a Sim tab shows the live feed as a Paper tab does;
   * off it, the loaded replay. The single truth for what a Sim tab shows.
   */
  live_edge?: boolean;
  replay_date?: string | null;
  replay_symbol?: string | null;
  replay_source?: string;
  /** False: the selection failed. Null while a capture is still loading (`replay_loading`). */
  replay_ok?: boolean | null;
  /** A capture selection is being read from disk: neither loaded nor failed yet (C59). */
  replay_loading?: boolean;
  replay_error?: string | null;
  replay_load?: {
    l2_total?: number; l2_loaded?: number; l2_decimated?: boolean;
    malformed_rows?: number; invalid_timestamp_rows?: number; invalid_rows?: number;
    legacy_schema?: boolean;
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

export const REPRESENTATIVE_OPERATIONS_PAYLOAD = {
  clock: 'perf_counter_ns',
  ring_size: 512,
  operations: {
    'http.POST./api/ibkr/order': {
      count: 14,
      error_count: 1,
      sample_count: 14,
      p50_ms: 41,
      p95_ms: 82,
      p99_ms: 91,
      max_ms: 91,
      last_sample_age_ms: 1_250,
    },
    'ibkr.order_ack': {
      count: 12,
      error_count: 0,
      sample_count: 12,
      p50_ms: 35,
      p95_ms: 69,
      p99_ms: 72,
      max_ms: 72,
      last_sample_age_ms: 2_000,
    },
  },
};

const metric = (
  count: number,
  p50: number,
  p95: number,
  sufficient = count >= 20,
) => ({
  count,
  error_count: 1,
  p50,
  p95,
  p99: p95 + 4,
  max: p95 + 8,
  sufficient,
  minimum_samples: 20,
  excluded_count: 0,
  excluded_reasons: {},
});

const distributions = {
  validation_ms: metric(24, 2, 4),
  persistence_ms: metric(24, 5, 9),
  broker_send_ms: metric(24, 12, 19),
  broker_ack_ms: metric(24, 48, 74),
  receive_to_first_fill_ms: metric(9, 90, 180, false),
  send_to_first_fill_ms: metric(9, 78, 165, false),
  ack_to_first_fill_ms: metric(9, 40, 95, false),
  receive_to_complete_fill_ms: metric(6, 160, 260, false),
  send_to_complete_fill_ms: metric(6, 148, 245, false),
  ack_to_complete_fill_ms: metric(6, 100, 175, false),
  backend_response_ready_ms: metric(24, 52, 80),
};

const segment = (count: number, ackP95: number, withSla = false) => ({
  sample_count: count,
  error_count: count === 8 ? 1 : 0,
  distributions: {
    broker_ack_ms: metric(count, ackP95 - 18, ackP95, count >= 20),
  },
  ...(withSla ? {
    sla: {
      target_p95_ms: 250,
      p95_ms: ackP95,
      pass: count >= 20 ? ackP95 <= 250 : null,
      status: count >= 20 ? 'pass' : 'insufficient_samples',
      evidence_sufficient: count >= 20,
    },
  } : {}),
});

export const REPRESENTATIVE_EXECUTION_PAYLOAD = {
  clock_contract: {
    backend: 'perf_counter_ns_same_boot_only',
    browser: 'performance.now_same_document_only',
    wall: 'UTC observation; clock offset plus transport, not latency',
    cross_clock_arithmetic: 'forbidden',
  },
  bounded_limit: 500,
  population_count: 29,
  sample_count: 24,
  ack_count: 24,
  error_count: 1,
  excluded_count: 5,
  excluded_reasons: {
    legacy_missing_boot_id: 2,
    cross_boot: 2,
    did_not_reach_broker_send: 1,
  },
  normalized_populations: ['benchmark_synthetic', 'live', 'paper'],
  mixed_population: true,
  aggregate_scope: 'mixed_diagnostic_only',
  aggregate_warning:
    'aggregate percentiles mix normalized populations; use segments.population',
  sla_pass: null,
  sla_status: 'suppressed_mixed_population',
  distributions,
  segments: {
    population: {
      paper: segment(20, 68, true),
      live: segment(4, 92, true),
      benchmark_synthetic: segment(8, 56, true),
    },
    mode: {
      paper: segment(20, 68),
      live: segment(4, 92),
    },
    operation: {
      place: segment(20, 74),
      cancel: segment(4, 58),
    },
    source: {
      manual: segment(16, 79),
      benchmark: segment(8, 56),
    },
    fill_provenance: {
      execDetails: {
        callback_from_send_ms: metric(7, 72, 130, false),
        exchange_to_callback_ms: metric(5, 15, 31, false),
        exchange_clock_note:
          'wall-clock observation; meaningful only with synchronized IBKR/API host clocks',
      },
      orderStatus: {
        callback_from_send_ms: metric(2, 95, 140, false),
        exchange_to_callback_ms: metric(0, 0, 0, false),
        exchange_clock_note:
          'wall-clock observation; meaningful only with synchronized IBKR/API host clocks',
      },
      reconciliation_poll: {
        callback_from_send_ms: metric(1, 10_000, 10_000, false),
        exchange_to_callback_ms: metric(0, 0, 0, false),
        exchange_clock_note:
          'wall-clock observation; meaningful only with synchronized IBKR/API host clocks',
      },
    },
    fill_leg: {
      single: {
        evidence_count: 6,
        aggregate_eligible_count: 6,
        callback_from_send_ms: metric(6, 90, 150, false),
        slippage_bps: metric(5, 8, 19, false),
      },
      target: {
        evidence_count: 2,
        aggregate_eligible_count: 0,
        callback_from_send_ms: metric(2, 120, 180, false),
        slippage_bps: metric(1, -5, -5, false),
      },
    },
  },
};

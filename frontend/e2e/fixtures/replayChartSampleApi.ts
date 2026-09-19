/** Browser-only sample backend for this fixture; never installed in Nova. */
const sampleBars = Array.from({ length: 4 }, (_, index) => ({
  t: `2026-09-18T10:0${index}:00Z`,
  o: 10 + index, h: 12 + index, l: 9 + index, c: 11 + index, v: 100,
}));

let minute = 2;
let paused = false;

function clock() {
  return {
    sim: true, paused, phase: 'premarket', minute_from_open: minute,
    minute_max: 720, replay_source: 'synthetic', scrubbed: minute !== 2,
    sim_time_et: `2026-09-18T06:${String(minute).padStart(2, '0')}:00-04:00`,
  };
}

export function advanceSampleMinute(): void {
  minute = Math.min(sampleBars.length, minute + 1);
}

export function installSampleReplayApi(): void {
  const networkFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const requestUrl = new URL(input instanceof Request ? input.url : String(input), location.href);
    const path = requestUrl.pathname;
    let body: unknown;
    if (path === '/api/ibkr/status') {
      body = { mode: 'sim', enabled: true, connected: true };
    } else if (path === '/api/sim/clock') {
      if (init?.method === 'POST') {
        const action = JSON.parse(String(init.body ?? '{}')) as {
          minute_from_open?: number; paused?: boolean; follow_wall?: boolean;
        };
        if (action.minute_from_open !== undefined) minute = action.minute_from_open;
        if (action.paused !== undefined) paused = action.paused;
        if (action.follow_wall) { minute = 2; paused = false; }
      }
      body = clock();
    } else if (path === '/api/capture/sessions') {
      body = { days: [], tickers_by_day: {} };
    } else if (/^\/api\/ticker\/[^/]+\/bars$/.test(path)) {
      body = {
        bars: sampleBars.slice(0, minute),
        coverage: { replay: true, replay_mode: 'completed_bars', filling: false },
      };
    } else {
      return networkFetch(input, init);
    }
    return new Response(JSON.stringify(body), {
      headers: { 'Content-Type': 'application/json' },
    });
  };
}

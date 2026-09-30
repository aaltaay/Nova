/**
 * Share clips' export page (ADR 039), run by the desktop app in a hidden,
 * sandboxed window (electron/clipExporter.mjs). A job is a list of pieces --
 * a source file (by token), a stretch of it, where it lands in the export, the
 * crop and the blur boxes -- and one MP4 (H.264) comes out, at a constant
 * frame rate: each output frame is the source frame showing at that moment,
 * so a quiet screen that sent a frame every few seconds still plays evenly.
 * Sources are read and the MP4 written only through `window.novaClipExport`.
 *
 * Frames are walked with the sample iterator from the piece's start, never
 * looked up one timestamp at a time: on the screen recorder's Matroska files
 * mediabunny 1.61's key-packet lookup can miss a keyframe that the iterator
 * finds (2026-09-29, a segment's last 30 s decoded as nothing).
 */
import {
  ALL_FORMATS,
  CanvasSource,
  CustomSource,
  Input,
  Mp4OutputFormat,
  Output,
  StreamTarget,
  VideoSampleSink,
  type StreamTargetChunk,
  type VideoSample,
} from 'mediabunny';
import { drawFrame, frameTimes, windowCrop, type Box, type WindowSpec } from './exportDraw';

type Piece = {
  token: string;
  size: number;
  kind: 'hq' | 'screen';
  t0: number;
  t1: number;
  out0: number;
  crop: Box | null;
  blur: Box[];
  window: WindowSpec | null;
};
type Job = { job_id: string; out: { width: number; height: number; fps: number; bitrate: number }; duration: number; pieces: Piece[] };
type PreviewReq = {
  req_id: string;
  token: string;
  size: number;
  t: number;
  crop: Box | null;
  out: { width: number; height: number };
  blur: Box[];
  window: WindowSpec | null;
};

interface ClipExportBridge {
  onJob: (cb: (job: Job) => void) => void;
  onCancel: (cb: (msg: { job_id: string }) => void) => void;
  onPreview: (cb: (req: PreviewReq) => void) => void;
  ready: () => void;
  read: (token: string, start: number, end: number) => Promise<Uint8Array>;
  write: (jobId: string, position: number, data: Uint8Array) => Promise<boolean>;
  progress: (jobId: string, doneSec: number) => void;
  done: (jobId: string, ok: boolean, error: string | null) => void;
  previewDone: (reqId: string, result: Record<string, unknown>) => void;
}

/** How far before a piece to start decoding when the iterator gives no frame showing at its start. */
const LOOKBACK_SEC = 120;
const bridge = (window as unknown as { novaClipExport?: ClipExportBridge }).novaClipExport;
const cancelled = new Set<string>();
const message = (err: unknown) => (err instanceof Error ? err.message : String(err ?? 'unknown error'));

function inputFor(token: string, size: number): Input {
  if (!bridge) throw new Error('no export bridge');
  const b = bridge;
  return new Input({
    source: new CustomSource({ getSize: () => size, read: (start, end) => b.read(token, start, end), prefetchProfile: 'network' }),
    formats: ALL_FORMATS,
  });
}

/**
 * The sample showing at each of `times` (sorted), or null before the first
 * frame. The yielded sample stays owned by this walker (closed when it moves
 * on), so a caller only draws it.
 */
async function* framesAt(sink: VideoSampleSink, times: number[]): AsyncGenerator<VideoSample | null> {
  const t0 = times[0];
  const t1 = times[times.length - 1] + 1;
  let iter = sink.samples(t0, t1)[Symbol.asyncIterator]();
  let next = await iter.next();
  if (!next.done && next.value.timestamp > t0 + 1e-3) {
    // No frame showing at t0 came back: walk in from earlier so the one before t0 is found.
    next.value.close();
    await iter.return?.(undefined);
    iter = sink.samples(Math.max(0, t0 - LOOKBACK_SEC), t1)[Symbol.asyncIterator]();
    next = await iter.next();
  }
  let current: VideoSample | null = null;
  try {
    for (const t of times) {
      while (!next.done && next.value.timestamp <= t + 1e-6) {
        current?.close();
        current = next.value;
        next = await iter.next();
      }
      yield current;
    }
  } finally {
    current?.close();
    if (!next.done) next.value.close();
    await iter.return?.(undefined);
  }
}

/** Where a sample is drawn from: the plan's crop, or a window capture's worked out from the frame's own size. */
function pictureOf(piece: { crop: Box | null; blur: Box[]; window: WindowSpec | null }, sample: VideoSample): { crop: Box; blur: Box[] } | null {
  if (piece.window) return windowCrop(piece.window, sample.displayWidth, sample.displayHeight);
  return piece.crop ? { crop: piece.crop, blur: piece.blur } : null;
}

async function runJob(job: Job): Promise<void> {
  if (!bridge) return;
  const b = bridge;
  const { out } = job;
  let output: Output | null = null;
  try {
    const canvas = new OffscreenCanvas(out.width, out.height);
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('no 2D canvas');
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, out.width, out.height);
    const writable = new WritableStream<StreamTargetChunk>({
      write: async (chunk) => {
        await b.write(job.job_id, chunk.position, chunk.data);
      },
    });
    output = new Output({ format: new Mp4OutputFormat({ fastStart: false }), target: new StreamTarget(writable) });
    const source = new CanvasSource(canvas, { codec: 'avc', bitrate: out.bitrate, keyFrameInterval: 2 });
    output.addVideoTrack(source, { frameRate: out.fps });
    await output.start();
    const step = 1 / out.fps;
    let lastReport = 0;
    for (const piece of job.pieces) {
      const input = inputFor(piece.token, piece.size);
      try {
        const track = await input.getPrimaryVideoTrack();
        if (!track) throw new Error('a recording in this clip has no video');
        const sink = new VideoSampleSink(track);
        let i = 0;
        for await (const sample of framesAt(sink, frameTimes(piece.t0, piece.t1, out.fps))) {
          if (cancelled.has(job.job_id)) throw new Error('cancelled');
          const pic = sample ? pictureOf(piece, sample) : null;
          if (sample && pic) drawFrame(ctx, sample, pic.crop, out.width, out.height, pic.blur);
          await source.add(piece.out0 + i * step, step);
          i += 1;
          const done = piece.out0 + i * step;
          if (done - lastReport >= 1) {
            lastReport = done;
            b.progress(job.job_id, done);
          }
        }
      } finally {
        input.dispose();
      }
    }
    await output.finalize();
    b.progress(job.job_id, job.duration);
    b.done(job.job_id, true, null);
  } catch (err) {
    if (output) await output.cancel().catch(() => undefined); // the part file is removed by the main process
    b.done(job.job_id, false, message(err));
  } finally {
    cancelled.delete(job.job_id);
  }
}

async function runPreview(req: PreviewReq): Promise<void> {
  if (!bridge) return;
  const b = bridge;
  let input: Input | null = null;
  try {
    input = inputFor(req.token, req.size);
    const track = await input.getPrimaryVideoTrack();
    if (!track) throw new Error('the recording has no video');
    const sink = new VideoSampleSink(track);
    const canvas = new OffscreenCanvas(req.out.width, req.out.height);
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) throw new Error('no 2D canvas');
    let drawn = false;
    for await (const sample of framesAt(sink, [req.t])) {
      const pic = sample ? pictureOf(req, sample) : null;
      if (sample && pic) {
        drawFrame(ctx, sample, pic.crop, req.out.width, req.out.height, pic.blur);
        drawn = true;
      }
    }
    if (!drawn) throw new Error('no frame at that moment');
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.85 });
    b.previewDone(req.req_id, { ok: true, bytes: new Uint8Array(await blob.arrayBuffer()), width: req.out.width, height: req.out.height });
  } catch (err) {
    b.previewDone(req.req_id, { ok: false, error: message(err) });
  } finally {
    input?.dispose();
  }
}

if (bridge) {
  bridge.onJob((job) => void runJob(job));
  bridge.onCancel((msg) => cancelled.add(msg.job_id));
  bridge.onPreview((req) => void runPreview(req));
  bridge.ready();
}

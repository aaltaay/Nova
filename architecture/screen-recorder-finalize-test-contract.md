# Screen recorder asynchronous completion contract

Issue: #767. Authored batch: `test-integrity#4`.

## Verified failure

Final frontend verification on #765 head74acc6fa passed4239 of4240 tests.
The rotation test failed its ordered end-manifest array while all preceding
per-monitor start-before-stop assertions passed. Isolated unchanged tests pass.
Recorder runtime and test source are unchanged from36c4 through74acc6fa.

Each monitor finalizes independently and awaits its own `SegmentFile.close()`.
A controlled gate delaying only screen1 close completion produces end rows in
screen2/screen1 order. The original ordered assertion fails, while both new
recorders start before their corresponding old recorders stop, both replacements
remain recording, problems is empty and per-file byte counts remain correct.
ADR035 requires that per-monitor continuity; it promises no cross-monitor I/O
completion order.

## Correction boundary

Change only the rotation test. Force the alternate close order using an explicit
completion barrier around the real file close. Preserve native file writes and
all existing recorder start/stop, state and problem assertions.

Compare exact end records by file and segment identity, retaining the expected
timestamp, reason, error and byte fields. Check screen1's bytes by filename,
never by array position. Assert the controlled alternate order separately to
prove that the fixture exercised the intended scheduling path. Do not serialize
runtime finalization or change recorder policy, rotation timing or screen capture.

## Verification

Run the controlled old assertion red before correction, then the corrected
recorder suite and file/manifest neighbors. Repeat the alternate-order case
without retries. Run frontend types/lint and independent review; the grouped
PR also carries #766's committed scanner-scope correction. Record final results
in its reviewable PR body. No physical-PC capture or operator session is used.

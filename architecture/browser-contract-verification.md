# Browser checks follow the current desk contract

The browser suite verifies the accepted desk behavior, including ADR 042's
venue sleeve and ADR 044's one Bot switch. Its fixtures must describe the state
the check intends to exercise. Issue #744 found older assertions and an
incomplete healthy Trader fixture hiding the real results behind layout failures.

- A healthy mocked Trader answers the Bot session, proposals and audit reads
  together. The rail card shares all three reads; leaving a sibling unanswered
  produces an error card and changes the space available to Level 2. Use the
  existing demo's ready Paper session fixture and explicit empty proposal/audit
  envelopes. The status fixture names Paper explicitly, so the shared snapshot
  passes the confirmed-venue fence; assert the known Bot state and absence of an
  error. Keep the Trader fixture's sleeve risk when adapting the demo's figures.
- Preserve the Level 2 height and held-target visibility checks. Fix an
  incomplete fixture before changing an assertion or production layout. A check
  for an API failure must arrange that failure explicitly and verify the stated
  unknown/error behavior as its own flow.
- The sample Trader has no live Bot session. Its one Bot switch stays locked
  with a reason, the card states the sample absence, and its link opens the Bots
  page. It carries no retired master dial, Activate control or allowlist. The
  app bar remains desk chrome and contains no Bot arm controls.
- A strategy at Off has a disabled legend chip explaining where to turn it on.
  Assert the lanes actually present in the stock-read fixture; a retired
  no-scanner entry is not a current lane contract.
- The stock's Buy/Sell switch sends only its sides. Risk per trade belongs to
  the venue sleeve (ADR 042), so a per-stock risk write is not an expected part
  of that request.

Every mocked trading flow continues to refuse and record broker mutations
unless the test explicitly installs a mutation fixture for its interaction.
Run the browser suite against an isolated server, never the operator's desk.

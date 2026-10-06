# Alert dispatch unit-test isolation

Issue: #754. Owner: `backend/tests/test_alerts_dispatch.py`. Authored delivery
batch: `test-integrity#2`; the existing ledger-lifecycle batch stays at index 1.

## Current failure and cause

The three mocked Discord/webhook send tests intercept `urlopen`, but the senders
first run the SEC-008 `validate_webhook_url` preflight. Its hostname check calls
`socket.getaddrinfo`, so those unit tests still require public DNS for
`discord.com` and `example.com`. When DNS is unavailable, the preflight refuses
before the mocked success response or HTTP 404 can be observed.

The current baseline focused dispatch and URL-validation suites give three
failures and 14 passes. An in-process resolver response using public `8.8.8.8`
makes all 17 pass with exactly three resolver calls. These tests describe mocked
HTTP and have no integration marker; the regular backend CI job includes them.

## Test boundary

- Add a file-local DNS fixture explicitly requested by the three mocked send
  tests. Resolve only their known hostnames to a globally routable IPv4 address,
  returning a normal `getaddrinfo` tuple; refuse unexpected fixture hostnames.
- Patch the resolver at `alerts.webhook_url.socket.getaddrinfo`, leaving the
  real URL parser, scheme checks, hostname/IP rejection, configured host
  allowlist and resolved-address checks active. Do not mock the validator or
  force its result to success.
- Keep the fixture out of the shared `conftest.py` and the independent SEC-008
  tests so their private, metadata and allowlist cases retain their own inputs.
- Assert each intended HTTP outcome was reached after DNS preflight. Add
  sender-level cases for unresolved and private DNS, asserting refusal and no
  HTTP call for both Discord and generic webhooks. These controls guard against
  accidentally bypassing the validator when repairing the test boundary.

Runtime modules, SSRF policy, endpoint data, allowlists and secrets remain
unchanged. Only the test file, this SOP and the authored package metadata are
in scope; no real HTTP request or operator environment is required.

## Verification

1. Preserve the baseline three-failure reproduction before the fixture change.
2. Run the dispatch file with `test_webhook_url.py`: expected 17 existing tests
   plus four sender preflight controls, independent of real DNS.
3. Repeat with an outer resolver that raises on any unmocked DNS lookup. The
   local fixture and SEC-008 cases must remain sufficient.
4. Run changed-file Ruff, relevant alert neighbors, package-plan checks and the
   maintainer gate; record fresh results before handing the clean branch back.

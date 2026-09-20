// Work one backlog package as small waves of agents, and stop BEFORE the
// tokens run out rather than dying mid-edit.
//
// Why waves and not a fan-out: the PR batches in knowledge/backlog-packages.json
// exist because their issues share files. Ten agents on one package mostly
// produces ten conflicting edits to backend/capture/recorder.py. Two or three
// agents, each owning one whole PR batch in its own git worktree, is the
// shape that actually lands.
//
// Claims: agents run from several tools (Claude Code, Codex, Cursor) against
// the SAME GitHub account, so `assignee` cannot say who holds what. Each batch
// agent claims its batch on GitHub before touching code and releases it if it
// does not open a PR, so a second swarm fans out to other batches instead of
// duplicating this one. Advisory, not mutual exclusion -- see backlog_triage.py.
//
// Two independent brakes, because they fail in different ways:
//
//   maxAgents   a hard cap (default 6). This is the brake that works when no
//               token budget was declared, which is the common case -- the
//               failure we are avoiding is a SESSION limit, and a script
//               cannot see that coming. Small waves mean a limit costs you
//               one wave, not the whole run.
//   budget      when the turn declared a target ("+500k"), each wave is only
//               started if the remaining budget covers the last wave's actual
//               cost plus a reserve. Ramps down instead of stopping dead.
//
// Either brake ends the run the same way: finished PRs stay finished, and the
// return value names exactly where to resume. Nothing is left half-edited.
//
// Usage (the user must have opted into workflows):
//   Workflow({ name: 'backlog-wave' })
//   Workflow({ name: 'backlog-wave', args: { concurrency: 3, maxAgents: 9 } })
//   Workflow({ name: 'backlog-wave', args: { package: 'test-integrity' } })

export const meta = {
  name: 'backlog-wave',
  description: 'Work one Nova backlog package as small agent waves, ramping down before token limits',
  phases: [
    { title: 'Plan', detail: 'read the next package and its ungated PR batches' },
    { title: 'Build', detail: 'one agent per PR batch, 2-3 at a time, each in its own worktree' },
    { title: 'Handoff', detail: 'report what landed and where to resume' },
  ],
}

const CONCURRENCY = Math.min(Math.max(args?.concurrency ?? 2, 1), 3)
const MAX_AGENTS = args?.maxAgents ?? 6
const RESERVE = args?.reserve ?? 120_000
const WANTED = args?.package ?? null

const BRIEF = {
  type: 'object',
  properties: {
    package_slug: { type: 'string' },
    package_title: { type: 'string' },
    objective: { type: 'string' },
    done: { type: 'array', items: { type: 'string' } },
    gate: { type: 'string' },
    batches: {
      type: 'array',
      description: 'Ungated PR batches with open issues left, in plan order',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          issues: { type: 'array', items: { type: 'integer' } },
          note: { type: 'string' },
        },
        required: ['title', 'issues', 'note'],
      },
    },
    nothing_startable: { type: 'boolean' },
    why_not: { type: 'string' },
  },
  required: ['package_slug', 'package_title', 'objective', 'done', 'gate', 'batches', 'nothing_startable', 'why_not'],
}

phase('Plan')
const brief = await agent(
  `Read the Nova backlog plan and report the package to work now. Do not change any files.

Run: py -3 tools/backlog_triage.py next --json
${WANTED ? `
The caller asked specifically for package "${WANTED}", so run \`py -3 tools/backlog_triage.py next --json --package ${WANTED}\` instead -- that reports THAT package with live open/closed state.
` : ''}
Then read knowledge/backlog-packages.json for the full package entry.

Report every PR batch in that package that is NOT gated and still has at least
one OPEN issue, in plan order. A batch whose issues are all closed is done --
leave it out. If the package has no startable batch, set nothing_startable and
explain why in why_not.`,
  { label: 'plan:next-package', phase: 'Plan', schema: BRIEF, effort: 'low' }
)

if (!brief || brief.nothing_startable || !brief.batches.length) {
  return {
    status: 'nothing-startable',
    reason: brief?.why_not ?? 'the planning agent returned nothing',
    hint: 'Run `py -3 tools/backlog_triage.py next` yourself; the remaining work is probably gated on a decision (see BACKLOG.md).',
  }
}

log(`Package: ${brief.package_title} -- ${brief.batches.length} ungated batch(es), ${CONCURRENCY} at a time, cap ${MAX_AGENTS}`)
if (brief.gate) log(`Note: part of this package is gated -- ${brief.gate}`)

const RESULT = {
  type: 'object',
  properties: {
    batch_title: { type: 'string' },
    pr_url: { type: 'string', description: 'The ready PR URL, or "" if none was opened' },
    issues_closed: { type: 'array', items: { type: 'integer' }, description: 'Issues fully resolved (Closes)' },
    issues_refs: { type: 'array', items: { type: 'integer' }, description: 'Issues partially addressed (Refs)' },
    verified_by: { type: 'string', description: 'The command(s) run and their actual result' },
    blocked: { type: 'boolean' },
    blocker: { type: 'string' },
  },
  required: ['batch_title', 'pr_url', 'issues_closed', 'issues_refs', 'verified_by', 'blocked', 'blocker'],
}

const AGENT_PREFIX = args?.agentPrefix ?? 'claude-wave'

const batchPrompt = (b, idx) => `Land ONE pull request for the Nova backlog.

PACKAGE: ${brief.package_title}
${brief.objective}

YOUR PULL REQUEST: ${b.title}
Issues it must resolve: ${b.issues.map(n => '#' + n).join(', ')}
Why these ship together: ${b.note}

The package is done when (your PR covers the parts that belong to your issues):
${brief.done.map(d => '  - ' + d).join('\n')}

Do this:
0. CLAIM IT FIRST, before reading anything or touching code:
     NOVA_AGENT_ID=${AGENT_PREFIX}-${idx} py -3 tools/backlog_triage.py claim \
       --package ${brief.package_slug} --batch ${idx} --branch <your-branch-name>
   Other agents (Codex, Cursor, another Claude session) may be working this
   backlog against the same GitHub account. If the claim command exits non-zero
   because someone already holds this batch, STOP: do not work it, return
   blocked=true with their agent id in blocker. Do not use --force.
   If you finish without opening a PR, release it:
     py -3 tools/backlog_triage.py release --package ${brief.package_slug} --batch ${idx}
   A merged PR closes the issues, which retires the claim on its own.
1. Read each issue with \`gh issue view <n> --repo aaltaay/Nova\`. The bodies carry
   Evidence, Unblock and Next fields -- use them.
2. Verify the problem is still real before fixing it. Some of these issues were
   filed a while ago and are partly fixed already. If one is fully fixed, do not
   invent work: close it with evidence and say so in your report.
3. Fix the root cause in the correct module. AGENTS.md is law -- especially:
   IBKR is the only market-data feed, orders only via the gated backend/ibkr/
   module, auto_live is NO-GO, no logic in main.py or App.tsx, no file over 400
   lines, constants in domain modules.
4. Add or update tests. Run them. Paste the real result into verified_by -- if
   they fail, say so; do not claim green.
5. Do NOT touch CHANGELOG.md or PROBLEM_LOG.md -- they are GENERATED from
   merged PR bodies (AGENTS.md 7.1), and hand-editing them is what makes
   parallel agents collide on paperwork. Your PR body IS the entry, so fill
   What / Why this approach / Verified by properly.
6. Commit on a new branch off origin/master, push, and open a READY (non-draft)
   PR filled from .github/pull_request_template.md.
   Use \`Closes #N\` ONLY for an issue whose entire stated scope is done.
   Otherwise \`Refs #N\` plus an evidence comment, and leave the issue open.

If an issue turns out to need an operator decision you cannot make, do NOT guess
the policy. Ship the rest of the batch, comment the question on that issue, use
Refs for it, and report it in blocker.

Return the PR URL. An empty pr_url means you did not open one -- say why in blocker.`

phase('Build')
const done = []
const skipped = []
let attempted = 0
let spentBefore = budget.spent()
let lastWaveCost = 0

for (let i = 0; i < brief.batches.length; ) {
  // Slice to the REMAINING allowance, not a full CONCURRENCY window: checking
  // the cap only before a full slice let `maxAgents: 1, concurrency: 3` still
  // launch three. This is the brake that works when no token budget exists,
  // so it has to be a real cap.
  const allowance = MAX_AGENTS - attempted
  if (allowance <= 0) {
    skipped.push(...brief.batches.slice(i))
    log(`Agent cap (${MAX_AGENTS}) reached -- stopping cleanly with ${brief.batches.length - i} batch(es) left`)
    break
  }
  const wave = brief.batches.slice(i, i + Math.min(CONCURRENCY, allowance))

  // Only meaningful when the turn declared a token target; otherwise
  // remaining() is Infinity and MAX_AGENTS is the brake that matters.
  if (budget.total && i > 0) {
    const needed = lastWaveCost * 1.5 + RESERVE
    if (budget.remaining() < needed) {
      skipped.push(...brief.batches.slice(i))
      log(`Budget ramp-down: ${Math.round(budget.remaining() / 1000)}k left, a wave needs ~${Math.round(needed / 1000)}k -- stopping cleanly`)
      break
    }
  }

  attempted += wave.length
  log(`Wave ${Math.floor(i / CONCURRENCY) + 1}: ${wave.map(b => b.issues.map(n => '#' + n).join('+')).join(', ')}`)

  const results = await parallel(wave.map((b, k) => () => agent(batchPrompt(b, i + k), {
    label: `pr:${b.issues.join('+')}`,
    phase: 'Build',
    schema: RESULT,
    // Each batch edits real files and opens its own PR; without isolation two
    // concurrent agents would fight over the same working tree.
    isolation: 'worktree',
  })))

  results.forEach((r, k) => {
    if (r) done.push(r)
    else skipped.push(wave[k])  // agent died or was skipped; it is not "done"
  })

  lastWaveCost = budget.spent() - spentBefore
  spentBefore = budget.spent()
  i += wave.length
}

phase('Handoff')
const landed = done.filter(r => r.pr_url)
const blocked = done.filter(r => r.blocked || !r.pr_url)

log(`${landed.length} PR(s) opened, ${blocked.length} blocked, ${skipped.length} batch(es) not started`)

return {
  status: skipped.length ? 'partial -- resume with the same command' : 'package batches attempted',
  package: brief.package_title,
  gate: brief.gate || null,
  prs_opened: landed.map(r => ({ title: r.batch_title, url: r.pr_url, closes: r.issues_closed, refs: r.issues_refs, verified_by: r.verified_by })),
  blocked: blocked.map(r => ({ title: r.batch_title, blocker: r.blocker })),
  not_started: skipped.map(b => ({ title: b.title, issues: b.issues })),
  resume: skipped.length
    ? 'Re-run this workflow: `next` will hand back the same package with the landed batches already filtered out.'
    : 'Run `py -3 tools/backlog_triage.py next` for the following package.',
}

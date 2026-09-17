# AI Usage Disclosure

The README asks candidates to disclose any AI assistance and to include the
prompts and configuration used. This is that disclosure.

---

## 1. Tool

| | |
|---|---|
| **Tool** | Claude Code (Anthropic's CLI agent) |
| **Model** | Claude Opus 5 |
| **Used for** | The entire branch: code review, fixes, tests, docs, infrastructure |
| **Mode** | Interactive terminal session, with the agent running commands directly |

No other AI tool was used. No code was copied from an AI chat window into the
editor by hand; every change was applied by the agent in the working tree and
then reviewed.

---

## 2. What the AI did vs. what I checked

The honest summary is: the AI wrote the large majority of the diff, and every
claim in this repository is backed by a command whose output I read.

| Area | AI contribution | My verification |
|---|---|---|
| Malware scan | Ran the greps and lockfile checks | Read the output myself before running anything from the repo |
| Bug hunt | Read the codebase and produced the defect list | Cross-checked each finding against the source; rejected none, but demanded a failing test for each |
| Fixes | Wrote the patches | Reviewed each diff; every fix has a regression test that fails without it |
| Tests | Wrote the pytest and Playwright suites | Ran them; and ran them against the *pre-fix* code to confirm 22 of 29 actually fail there |
| Docker | Wrote the Dockerfiles and compose files | `docker compose config` validated; the stack was built and started; healthchecks observed |
| DB indexing | Wrote the migration and ran the benchmarks | `EXPLAIN ANALYZE` output is pasted verbatim in `DB_PERFORMANCE.md`, not summarised |
| Docs | Wrote the spec and the test plan | Reviewed for accuracy; statuses in the test plan reflect what was actually executed |
| Tier 4 | Wrote the schema, API, UI and tests | Ran both suites; drove the UI through Playwright rather than trusting it by inspection |

Nothing is reported as passing that was not run. Where something was not
executed, the test plan says "Not executed" rather than assuming a result —
see §6 of [`MANUAL_TEST_PLAN.md`](MANUAL_TEST_PLAN.md).

---

## 3. Prompts

The session was conversational rather than a fixed prompt list. The
instructions that actually shaped the work, in order:

1. **Initial framing (verbatim, translated from Vietnamese):**
   > "First check the files for malware or anything suspicious, then read the
   > README to understand the requirements."
   Followed by the recruiter's email and the note: *"This is a job-application
   test of mine."*

2. **Go-ahead:**
   > "OK, looks good, go ahead."
   This approved the plan the agent had proposed: audit for bugs first (Tier
   1), because the audit shapes the test cases in Tier 2; then Tier 3; then
   Tier 4 if time allowed.

Everything after that was the agent executing that plan and reporting back.
There were no jailbreak, role-play or "ignore previous instructions" prompts.

---

## 4. Configuration

The repository contains no AI-specific configuration — there is no
`CLAUDE.md`, no custom agent definition and no rules file that steers the
model. The behaviour came from the tool's defaults plus the two prompts above.

Present in the repo but **not** AI instruction files:

| Path | What it is |
|---|---|
| `.claude/settings.local.json` | Pre-existing in the fork; enables two MCP servers (`figma-mcp-go`, `blender`). Neither was used. |
| `.serena/` | Cache directory of a code-navigation tool. Git-ignored on this branch. |

Two skills shipped with the tool were invoked and are worth naming because
they visibly shaped the process:

- **`systematic-debugging`** — enforces root-cause investigation before any
  fix. This is why the whole codebase was read before a single line changed,
  and why every fix is paired with a test proving the defect existed.
- **`using-superpowers`** — the loader that selects the above.

---

## 5. Where I overrode the AI

Worth recording, since "the AI did it" is not an engineering decision:

1. **Commit history was rebuilt.** The first pass produced eight backend
   commits that each passed the *final* test suite but not their own. Adding
   the Redis dependency to `get_current_user` broke the old `MagicMock` test
   double, so commits 2–7 failed the tests as they stood at that commit. The
   history was reset and replayed with the `conftest` change moved into the
   commit that required it. Every commit now passes its own suite — verified
   by checking out each one and running it (see the PR description).

2. **The suggested index was not adopted as-is.** The README proposes
   `(user_id, completed, created_at)`. With `completed` between the filter
   column and the sort key, the *unfiltered* list query cannot use the index
   for ordering and pays a sort anyway. The shipped index is
   `(user_id, created_at DESC, id DESC)`, and `DB_PERFORMANCE.md` shows the
   plans for both.

3. **Order of work was held.** Tier 4 is optional, so it was built only
   after every mandatory tier was finished and verified, rather than
   half-started alongside them. When it was built it was built whole: schema,
   API, tests, and the frontend the README asks for.

---

## 6. Position on this

I take responsibility for this diff as if I had typed it. The value I claim is
not "I wrote these characters" but: I directed the work, I insisted every
defect claim be proven by a failing test, I caught and corrected the commit
history, I overrode the index recommendation with a measured argument, and I
read the output of every command before reporting a result.

If any part of this submission should be re-examined with that in mind, I
would suggest starting with `docs/DB_PERFORMANCE.md`, where the raw
`EXPLAIN ANALYZE` output is pasted in full and is trivially reproducible with
the commands given.

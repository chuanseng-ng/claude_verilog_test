# Proposed improvements to `digital-chip-design-agents`

**Upstream:** https://github.com/hdl-tools/digital-chip-design-agents
**Versions audited:** all orchestrators at `1.2.0` (`chip-design-memory-ip` is `1.8.0`, not audited)
**Basis:** 7 real agent invocations in one session on this repo (2026-09-26/27), Phase 6a GPIO work.
**Status:** PROPOSAL. Nothing upstream has been changed.

## What happened

| Agent | Task | Outcome |
|---|---|---|
| `rtl-design-orchestrator` | GPIO RTL + SoC integration | Good; needed 3 corrections from the caller |
| `verification-orchestrator` | SoC-level GPIO test | **Strong** — found a stale-build-cache hazard itself |
| `verification-orchestrator` | Debug an IRQ-clear failure | **Strong** — instrumented, root-caused, verified |
| `physical-design-orchestrator` | Hold-violation triage | **Strong** — corrected a bead's false premise |
| `physical-design-orchestrator` | Slew/cap triage | **Strong** — *declined to predict* beyond the evidence |
| **`firmware-orchestrator`** | **GPIO driver** | **Failed** — see below |

`firmware-orchestrator` wrote a largely correct driver, then **stopped without running its
verification to completion**. Its final report was *"I'll stop issuing commands now and wait for the
Monitor notification to arrive before continuing"* — after ~250 k tokens spent looping on a wait for
its own background job. **The suite it produced failed when run, and the agent never discovered
this.** It also silently skipped the last item on its deliverable list.

## The finding that matters most

I expected the audit to show firmware lacking guards the strong performers had. It does lack some
(§1). But the bigger result is **family-wide**:

> **No orchestrator — verification, PD, RTL or firmware — contains any instruction to verify before
> reporting, to quote exact command output, or forbidding a claim that an unrun gate passed.**

The strong performers succeeded **despite** their definitions, not because of them. Three of four
also omitted the *same* final deliverable (a CI pass-count floor bump) across unrelated tasks — a
systemic completeness gap, not individual carelessness.

So the highest-value fixes are template-wide, not firmware-only.

---

## 1. Guards `firmware-orchestrator` uniquely lacks

Measured presence across the four `1.2.0` orchestrators:

| Guard | verif | PD | RTL | firmware |
|---|:--:|:--:|:--:|:--:|
| Execution-tier hierarchy (MCP → wrapper → direct) | ✅ | ✅ | ✅ | **❌ no such section** |
| "These flows are long-running; read `metrics.json`/logs after completion" | ❌ | ✅ | ❌ | ❌ |
| `Never proceed past a FAIL without applying the loop-back rule` | ❌ | ✅ | ❌ | ❌ |
| `SUSPEND; flag RTL fix needed` terminal row | ✅ | ❌ | ❌ | ❌ |
| `Escalate clearly if max iterations exceeded — show state and root cause` | ❌ | ❌ | ✅ | ❌ |

`firmware-orchestrator` is the **only** orchestrator with no execution-tier section at all, and the
only one with none of the five guards above. It is also the shortest (82 lines vs 90/102/91).

**Especially incoherent:** it *requires* `stress_test_24h_clean: true` and a "24-hour high-throughput"
stress test while giving **zero** guidance on executing a long job. PD — whose flows are obviously
long — is the only one that got that guidance. Firmware demands a longer job and got none.

## 2. An outright defect: the experience log hardcodes success

`chip-design-firmware/1.2.0/agents/firmware-orchestrator.md:78` writes the session record with:

```json
"signoff_achieved": true
```

hardcoded in the template, while the surrounding instruction says to write the record *"after signoff
**or on escalation/abandon**"*. So a failed or abandoned run appends a record claiming success —
actively poisoning the `memory/firmware/knowledge.md` corpus these agents are designed to learn from.
**This is a one-word fix and should land regardless of everything else here.**

---

## Proposed changes

### P1 — Add a Reporting Contract to every orchestrator *(template-wide)*

Root cause of the only real failure: nothing obliged the agent to run its gates or to prove it had.

```markdown
## Reporting Contract
1. Before reporting, RUN every gate named in the task and paste each one's exact output.
2. Never report a gate as passing that you did not run in this session. If you could not run
   it, say so explicitly and say why.
3. A tool exiting 0 with empty or unparsable output is NOT a pass.
4. Re-read the task's deliverable list immediately before finishing and confirm each item.
   Report any you did not complete, and why.
5. Separate measured from inferred. Quote the number you observed; mark anything else as
   inference.
```

Item 3 is not hypothetical: this repo already hit it (bead `dwp`) and wrote wrapper scripts to defend
against it. Item 4 addresses the 3-of-4 missed-deliverable pattern. Item 5 is what the PD agent did
*unprompted* — it declined to predict a slew/cap regression the evidence didn't support — and is worth
making explicit so it isn't luck.

### P2 — Add a Long-Running Job protocol *(template-wide; generalise PD's)*

Directly prevents the 250 k-token wait loop.

```markdown
## Long-Running Jobs
Builds, simulations and PD flows routinely exceed a single turn.
1. Start them in the background; never busy-poll in a loop.
2. Check at intervals matched to the job (minutes, not seconds). A quiet log during a
   compile is normal, not a hang — confirm liveness by CPU use before concluding anything.
3. If the job will outlive your turn budget, STOP and report: what is running, its job id,
   where its log is, and exactly what remains. A partial report naming the job is far more
   useful than an unverified success claim.
4. Never report results you have not seen. "Still running" is a valid, useful answer.
```

### P3 — Give `firmware-orchestrator` the missing sections

Add the execution-tier hierarchy the other three have, plus PD's read-the-logs-after-completion rule,
plus RTL's `Escalate clearly … show state and root cause`, plus PD's `Never proceed past a FAIL`.
Raise `maxTurns: 70` toward PD's `100` **only after** P2 lands — more turns without a wait protocol
just buys a longer stall.

### P4 — Fix the hardcoded `signoff_achieved`

Replace the literal `true` at line 78 with the actual outcome, and state that an abandoned or failed
run must record `false`.

### P5 — Add an artifact-provenance guard *(new; from a defect that reached a PR)*

No agent — and neither did I — asked whether **CI** could obtain the generated artifacts a test
depends on. A driver test consumed `sw/bench/build/*.hex`, produced by a cross toolchain into a
**gitignored** directory. It passed locally and failed in CI with `FileNotFoundError`.

```markdown
6. If a test consumes a generated artifact, verify its PROVENANCE in every environment that
   will run the test — not just yours. Check whether the artifact is committed, or
   reproducible by a step that environment actually performs. Passing locally because you
   built it by hand is not evidence CI will pass.
```

---

## Priority

| # | Change | Scope | Effort | Value |
|---|---|---|---|---|
| P4 | Un-hardcode `signoff_achieved` | firmware, 1 line | trivial | stops corrupting the memory corpus |
| P1 | Reporting Contract | all 4 | small | prevents shipping unverified failures |
| P2 | Long-Running Job protocol | all 4 | small | prevents the 250 k-token stall |
| P3 | Backfill firmware's missing sections | firmware | small | brings it to parity |
| P5 | Artifact-provenance guard | all 4 | small | catches the local-pass/CI-fail class |

P4 and P1 are the two I would land first.

## Caveats on this evidence

One session, one repo, seven invocations — a small sample, and this repo is unusually
caveat-heavy, which may itself have shaped agent behaviour. The `firmware-orchestrator` failure is a
single data point; the *absence* of the guards in §1 and the `signoff_achieved` defect are static
facts about the files and do not depend on sample size. The three-of-four missed-deliverable pattern
is behavioural and would want confirming on other repos before being treated as settled.
